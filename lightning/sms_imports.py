"""Bank SMS into the ledger, reviewed (milestone 3).

`parse_sms` reads one bank message into a proposed transaction, or None when it is not one (a one-time code, a
declined payment, an offer). `SmsImportService.read` turns new messages into rows of the reviewed bank import
(`bank_imports.BankImportService.stage`), one batch per account, so the owner confirms every row on the same
review screen as a CSV statement, with its duplicate checks. Nothing is posted without that review.

An account is found by the last four digits the bank names ("…0285"); the first time, the owner says which
account they belong to and Lightning remembers. Messages read before are skipped by their fingerprint. The
patterns follow the owner's CIB and NBE messages (Arabic, `tests/fixtures/bank_sms.json`); each bank is added
from its samples.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

from lightning.core.dates import today
from lightning.core.errors import ValidationError

ENDINGS_KEY = "sms_account_endings"   # {"0285": account_id}
SEEN_KEY = "sms_seen"                  # messages already read, newest last: "fp" (text only) or "fp@ms" (inbox)
WAITING_KEY = "sms_waiting"            # parsed messages whose account ending is not known yet
BALANCES_KEY = "sms_stated_balances"   # {account_id: {"balance", "date", "dismissed"}}: the newest balance a message stated
UNREAD_KEY = "sms_unread"              # messages with an amount that no rule could read: never dropped unseen
LAST_READ_KEY = "sms_last_read_ms"     # the phone's inbox is read from here on
QUIET_KEY = "sms_quiet_senders"        # {"Vodafone365": dismissals}: senders whose unreadable messages are offers
BANK_SENDERS_KEY = "sms_bank_senders"  # senders that sent a message a rule read: never made quiet
QUIET_AFTER = 2                        # dismissing this many of a sender's unreadable messages quiets it
MAX_UNREAD = 200
OVERLAP_MS = 10 * 60 * 1000            # the inbox is re-read this far before the cursor: late arrivals are not lost
PAIR_MINUTES = 30                      # an own transfer's two messages arrive within this
FIRST_LOOK_DAYS = 30                   # the first read goes this far back
PERSON = re.compile(r"^\+?\d{7,}$")     # a phone number: a person, not a bank's sender name or short code
SALARY_ENDING = "salary"               # the salary message names no account: its own remembered choice
MAX_SEEN = 5000
MAX_TEXT = 1000

# Arabic digits plus the Arabic decimal mark (U+066B) and thousands mark (U+066C) as plain ASCII
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
_NUM = r"([\d,]+(?:\.\d{1,2})?)"
_CUR = r"(?:EGP|جم|ج\.م\.?|جنيه)"
_AMOUNT = _CUR + r"?\s*" + _NUM + r"\s*" + _CUR + r"?"
_ENDING = r"(?:(?:المنتهية|المنتهي)\s*ب[ـ]?|رقم)\s*[*•xX]*\s*(\d{4})"
_CLOCK = r"(?:\s*(?:الساع[هة])?\s*(\d{1,2}:\d{2}))?"
_IGNORE = re.compile(r"(OTP|one[- ]time|رمز\s*(?:التحقق|التفعيل|المرور)|كلمة\s*(?:السر|المرور)|"
                     r"رفض|مرفوض|لم\s*تتم|declined|was not|unsuccessful|غير\s*ناجح)", re.IGNORECASE)
BANK_PHONES = {"19666": "CIB", "19623": "NBE"}


@dataclass(frozen=True)
class SmsTransaction:
    kind: str            # "withdrawal" (cash), "purchase", "transfer_out", "transfer_in", "salary"; "money_out" or
                         # "money_in" when only the general rule read it
    amount: Decimal      # positive; `signed` gives the ledger's sign
    ending: str          # the account's or card's last four digits, or SALARY_ENDING
    when: str            # ISO date and time, from the message or when it arrived
    place: str = ""      # merchant, ATM, or who sent or received a transfer
    reference: str = ""
    balance: Decimal | None = None
    bank: str = ""
    sure: bool = True    # False when only the general rule read it: the review says to check it
    text: str = ""       # the message itself, shown beside its row on the review (IV-3AU 3AU2)

    @property
    def inflow(self) -> bool:
        return self.kind in ("transfer_in", "salary", "money_in")

    @property
    def signed(self) -> Decimal:
        return self.amount if self.inflow else -self.amount


def _amount(text: str | None) -> Decimal | None:
    try:
        value = Decimal((text or "").replace(",", ""))
    except InvalidOperation:
        return None
    return value if value > 0 else None


def _when(day: str | None, clock: str | None, received: datetime, *, month_first: bool = False) -> str:
    """dd/mm/yy, dd-mm-yyyy, or mm-dd without a year (NBE's InstaPay), and hh:mm; the arrival time when the
    message has none. A date without a year is the latest one not after the message arrived."""
    hour, minute = received.hour, received.minute
    if clock:
        hour, minute = (int(p) for p in clock.split(":"))
    if day:
        parts = [int(p) for p in re.split(r"[/-]", day)]
        try:
            if len(parts) == 3:
                d, m, y = parts
                return datetime(y + 2000 if y < 100 else y, m, d, hour, minute).isoformat(timespec="minutes")
            if len(parts) == 2:
                m, d = parts if month_first else parts[::-1]
                moment = datetime(received.year, m, d, hour, minute)
                if moment.date() > received.date():
                    moment = moment.replace(year=received.year - 1)
                return moment.isoformat(timespec="minutes")
        except ValueError:
            pass
    return received.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="minutes")


def _place(raw: str | None) -> str:
    """A merchant as the bank pads it ("Uber                  Dow"): the name, without the city code."""
    parts = [p for p in re.split(r"\s{2,}", (raw or "").strip(" ,")) if p]
    if len(parts) > 1 and len(parts[-1]) <= 4:
        parts = parts[:-1]
    return " ".join(" ".join(parts).split())


def _clean(text: str) -> str:
    return " ".join(text.translate(_DIGITS).replace("،", ",").split())


def parse_sms(text: str, *, sender: str = "", received: datetime | None = None) -> SmsTransaction | None:
    """One bank message as a proposed transaction, or None when it moves no money (a code, a declined payment,
    an offer). Patterns: CIB and NBE in Arabic (`tests/fixtures/bank_sms.json` holds a sample of each)."""
    received = received or datetime.now()
    body = (text or "").translate(_DIGITS).replace("،", ",")[:MAX_TEXT]  # spaces kept: they bound merchants
    flat = " ".join(body.split())
    if not flat or _IGNORE.search(flat):
        return None
    bank = next((name for phone, name in BANK_PHONES.items() if phone in flat), "")
    bank = bank or next((name for name in BANK_PHONES.values() if sender.upper().startswith(name)), "") \
        or ("CIB" if "CIB" in flat.upper() else sender)
    balance_match = re.search(r"(?:الرصيد\s*المتاح|المتاح)\s*" + _AMOUNT, flat)
    balance = _amount(balance_match.group(1)) if balance_match else None
    on = r"(?:في|بتاريخ|يوم)\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)" + _CLOCK

    # A debit card. CIB: "تم سحب مبلغ EGP 5000.00 من بطاقة الخصم المباشر المنتهية بـ **1234 من <ATM> في
    # 04/10/26 19:28" (cash). NBE: "تم خصم 147.87 EGP من بطاقة الخصم المباشر رقم 1234 عند <merchant> يوم
    # 06/10/26 الساعه 11:13 المتاح 3792.36EGP" (a purchase).
    card = re.search(r"تم\s*(سحب|خصم|شراء)\s*(?:مبلغ)?\s*" + _AMOUNT + r"\s*من\s*بطاقة.*?" + _ENDING +
                     r"\s*(?:(?:من|لدى|في|عند)\s+(.+?))?\s*" + on, body, re.S)
    if card:
        verb, raw, ending, place, day, clock = card.groups()
        amount = _amount(raw)
        if amount is None:
            return None
        return SmsTransaction("withdrawal" if verb == "سحب" else "purchase", amount, ending,
                              _when(day, clock, received), _place(place), balance=balance, bank=bank)

    # InstaPay, CIB: "تم تنفيذ تحويل لحظي بمبلغ 2000.00 جم من حسابك المنتهي بـ ****1234 برقم مرجعي ab12 بتاريخ
    # 01-10-2026 11:05" (out), "… إلى حسابك المنتهي بـ ****1234 من <name> برقم مرجعي …" (in).
    cib = re.search(r"تحويل\s*لحظي\s*بمبلغ\s*" + _AMOUNT + r"\s*(من|إلى|الى)\s*حسابك\s*" + _ENDING +
                    r"\s*(?:من\s+(.+?)\s+)?(?:برقم\s*مرجعي\s*([0-9A-Za-z]+))?\s*" + on, flat)
    if cib:
        raw, direction, ending, who, reference, day, clock = cib.groups()
        amount = _amount(raw)
        if amount is None:
            return None
        return SmsTransaction("transfer_out" if direction == "من" else "transfer_in", amount, ending,
                              _when(day, clock, received), (who or "").strip(), reference or "",
                              balance, bank)

    # InstaPay, NBE: "تم إضافة تحويل لحظي لحسابكم رقم 1234 بمبلغ 30.00 جم من <name> رقم مرجعي 1586 يوم 10-05
    # الساعة 11:16" (in; the date is month-day), "تم تنفيذ تحويل لحظي من حسابكم رقم 1234 بمبلغ … جم إلى <name> …"
    nbe = re.search(r"تم\s*(إضافة|اضافة|تنفيذ)\s*تحويل\s*لحظي\s*(?:لحساب\S*|من\s*حساب\S*)\s*" + _ENDING +
                    r"\s*بمبلغ\s*" + _AMOUNT + r"\s*(?:من|إلى|الى)\s+(.+?)\s+(?:ب?رقم\s*مرجعي\s*([0-9A-Za-z]+))?\s*"
                    + on, flat)
    if nbe:
        verb, ending, raw, who, reference, day, clock = nbe.groups()
        amount = _amount(raw)
        if amount is None:
            return None
        return SmsTransaction("transfer_out" if verb == "تنفيذ" else "transfer_in", amount, ending,
                              _when(day, clock, received, month_first=True), who.strip(), reference or "",
                              balance, bank)

    # Salary, CIB: "عميلنا العزيز لقد تم تحويل مبلغ EGP19,584.66 على حسابكم لدينا من جهة العمل"
    salary = re.search(r"تحويل\s*مبلغ\s*" + _AMOUNT + r"\s*(?:على|الى|إلى)\s*حساب\S*.*?جهة\s*العمل", flat)
    if salary:
        amount = _amount(salary.group(1))
        if amount is None:
            return None
        return SmsTransaction("salary", amount, SALARY_ENDING, _when(None, None, received), "Salary", bank=bank)
    return _general(flat, received, balance, bank)


_OUT_WORDS = r"(charged|خصم|سحب|شراء|سداد|دفع|مدفوعات|تحويل\s*لحظي\s*من|تحويل\s*من\s*حساب|debited|withdraw\w*|purchase|paid|spent|sent)"
_IN_WORDS = r"(إضافة|اضافة|إيداع|ايداع|استلام|استرداد|لحسابكم|إلى\s*حسابك|الى\s*حسابك|credited|received|deposit\w*|refund\w*)"


# An offer, not a payment (owner, 2026-11-01: Nawy and Vodafone offers were kept as bank messages): a link, a dial
# code, or the words offers use. A bank's own payment message carries none of these; a known pattern still reads it.
_AR_START = r"(?<![\u0600-\u06FF])(?:و|ب|ل|ف)?(?:ال)?"  # an Arabic word's start, with its usual prefixes: not inside معرض
_PROMO = re.compile(r"(https?://|www\.|\.link/|\*\d{2,}#|\boffers?\b|\bpromo|\brefer\b|\binvite|limited time|\bwin\b|"
                    r"\bfree\b|cashback|" + _AR_START + r"(?:عرض|عروض|باق[ةه]|باقتك|اشتراك|اشترك|اشحن|شحن\s*رصيد|هدي[ةه]|"
                    r"بلاش|مجان|اربح|كوبون|اكسب|استمتع)|خصم\s*\d+\s*%|\d+\s*%\s*خصم)", re.IGNORECASE)
# Something that says money moved in an account, a card or a wallet.
_ACCOUNTISH = re.compile(_OUT_WORDS + "|" + _IN_WORDS + r"|حساب|بطاق[ةه]|محفظ|الرصيد|رصيدك|عملية|account|card|wallet|"
                         r"balance|transaction|" + "|".join(BANK_PHONES), re.IGNORECASE)


_CARD_LIMIT = re.compile(r"available\s*limit|credit\s*limit|الحد\s*المتاح|الحد\s*الائتماني", re.IGNORECASE)


def is_offer(text: str) -> bool:
    return bool(_PROMO.search(_clean(text or "")))


def looks_like_money(text: str) -> bool:
    """A message the owner should see even when no rule reads it: an amount with a currency, said about an account,
    a card or a wallet, and not an offer. Codes, declined payments, adverts and bundles are not money."""
    flat = _clean(text or "")
    return (bool(re.search(_CUR + r"\s*" + _NUM + r"|" + _NUM + r"\s*" + _CUR, flat)) and not _IGNORE.search(flat)
            and bool(_ACCOUNTISH.search(flat)) and not _PROMO.search(flat))


def prefill(text: str) -> dict:
    """What a kept message (one no rule read) can still fill on the Add sheet: its first amount with a currency and
    which way the money went, when the words say. The person checks the rest; nothing is saved here."""
    flat = _clean(text or "")
    money = re.search(_CUR + r"\s*" + _NUM + r"|" + _NUM + r"\s*" + _CUR, flat)
    amount = ""
    if money:
        try:
            amount = format(Decimal((money.group(1) or money.group(2)).replace(",", "")), "f")
        except (InvalidOperation, AttributeError):
            amount = ""
    inflow = bool(re.search(_IN_WORDS, flat, re.IGNORECASE)) and not re.search(_OUT_WORDS, flat, re.IGNORECASE)
    day = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", flat)
    when = _when(day.group(1), None, datetime.now())[:10] if day else ""  # the message's own date
    place = re.search(r"(?:عند|لدى|\bat)\s+(.+?)(?=\s+(?:يوم|في|on|بتاريخ|\d)|$)", flat)
    return {"amount": amount, "kind": "in" if inflow else "out", "date": when,
            "counterparty": place.group(1).strip() if place else ""}


def _general(flat: str, received: datetime, balance: Decimal | None, bank: str) -> SmsTransaction | None:
    """The general rule, for a wording no bank pattern knows yet: an amount with its currency, an account or
    card ending, and words that say which way the money went. All three, or nothing."""
    money = re.search(_CUR + r"\s*" + _NUM + r"|" + _NUM + r"\s*" + _CUR, flat)
    ending = re.search(r"(?:رقم|المنتهي\S*\s*ب[ـ]?|ending(?:\s*(?:with|in))?|[*xX•]{2,})\s*[*xX•]*\s*(\d{4})\b", flat,
                       re.IGNORECASE)
    out_word = re.search(_OUT_WORDS, flat, re.IGNORECASE)
    in_word = re.search(_IN_WORDS, flat, re.IGNORECASE)
    if not money or not ending or bool(out_word) == bool(in_word) or _PROMO.search(flat):
        return None
    amount = _amount(money.group(1) or money.group(2))
    if amount is None:
        return None
    day = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?:\D{0,12}?(\d{1,2}:\d{2}))?", flat)
    place = re.search(r"(?:عند|لدى|\bat)\s+(.+?)(?=\s+(?:يوم|في|on|بتاريخ|\d)|$)", flat)
    return SmsTransaction("money_in" if in_word else "money_out", amount, ending.group(1),
                          _when(day.group(1) if day else None, day.group(2) if day else None, received),
                          place.group(1).strip() if place else "", balance=balance, bank=bank, sure=False)


def fingerprint(text: str) -> str:
    return hashlib.sha256(_clean(text or "").encode("utf-8")).hexdigest()[:32]


KIND_NOTES = {"withdrawal": "Cash withdrawal", "purchase": "Card purchase", "transfer_out": "InstaPay sent",
              "transfer_in": "InstaPay received", "salary": "Salary", "money_out": "Money out", "money_in": "Money in"}


class SmsSource(Protocol):
    """Where bank messages come from on a phone (the Android app's `SmsBridge`); tests use a fake."""

    def permission(self) -> str: ...            # "granted", "not_granted" or "unavailable"
    def request(self) -> None: ...              # show the system's permission question
    def since(self, after_ms: int) -> list[tuple[str, str, int]]: ...  # (sender, body, received ms), oldest first
    def take_shared(self) -> list[str]: ...     # texts shared into Lightning since last asked


class SmsImportService:
    """Reads bank messages into the bank import's review, one batch per account."""

    def __init__(self, db, settings, accounts, bank_imports):
        self.db, self.settings, self.accounts, self.bank_imports = db, settings, accounts, bank_imports

    def _json(self, key: str, empty):
        try:
            value = json.loads(self.settings.get(key) or "null")
        except ValueError:
            return empty
        return value if isinstance(value, type(empty)) else empty

    def endings(self) -> dict[str, int]:
        """Resolve saved account codes and legacy local ids to this database's ids."""
        result = {}
        for ending, value in self._json(ENDINGS_KEY, {}).items():
            text = str(value)
            account_id = int(text) if text.isdigit() else self.db.scalar("SELECT id FROM accounts WHERE code=?", (text,))
            if account_id is not None:
                result[str(ending)] = int(account_id)
        return result

    def account_for(self, ending: str) -> int | None:
        """The account a card or account ending was told to be (once, by the person), if it is still usable."""
        account_id = self.endings().get(ending)
        if account_id is None:
            return None
        usable = {a.id for a in self.accounts.list(active_only=True) if a.currency == "EGP"}
        return account_id if account_id in usable else None

    def mark_seen(self, text_fingerprint: str) -> None:
        """A message entered by hand on the Add sheet is read: the phone's inbox must not offer it again."""
        if not re.fullmatch(r"[0-9a-f]{32}", text_fingerprint or ""):
            return
        seen = self._json(SEEN_KEY, [])
        kept = self._json(UNREAD_KEY, [])
        left = [m for m in kept if str(m.get("id", "")).split("@")[0] != text_fingerprint]
        if text_fingerprint not in seen or len(left) != len(kept):
            with self.db.transaction():  # a kept message entered by hand leaves From SMS (it said: until you enter it)
                if text_fingerprint not in seen:
                    self.settings.set(SEEN_KEY, json.dumps((seen + [text_fingerprint])[-MAX_SEEN:]))
                if len(left) != len(kept):
                    self.settings.set(UNREAD_KEY, json.dumps(left))

    def waiting(self) -> list[dict]:
        """Messages read whose account is not known yet, grouped by ending: [{"ending", "count", "total"}]."""
        groups: dict[str, dict] = {}
        for item in self._json(WAITING_KEY, []):
            group = groups.setdefault(item["ending"], {"ending": item["ending"], "count": 0, "kinds": set(),
                                                       "banks": set()})
            group["count"] += 1
            group["kinds"].add(item["kind"])
            if item.get("bank"):
                group["banks"].add(str(item["bank"]))
        return [dict(g, kinds=sorted(g["kinds"]), banks=sorted(g["banks"])) for g in groups.values()]

    def choices(self) -> list:
        """The accounts an ending can be: active EGP bank accounts first, then wallets (a bank's card is never cash
        at hand, so that is left out)."""
        usable = [a for a in self.accounts.list(active_only=True) if a.currency == "EGP"
                  and (a.account_type.value == "BANK" or (a.account_type.value == "CASH" and not a.cash_at_hand))]
        return sorted(usable, key=lambda a: a.account_type.value != "BANK")

    def guess(self, ending: str, banks: list[str]) -> int | None:
        """The account an ending most likely is, offered ready on From SMS and confirmed by one tap (never posted
        unasked): the one whose saved last four digits are the ending, else the only bank account of the bank
        that sent the messages, else (no bank named) the only bank account there is."""
        options = self.choices()
        same = [a.id for a in options if (a.last4 or "").strip()[-4:] == ending and ending != SALARY_ENDING]
        if len(same) == 1:
            return same[0]
        bank_accounts = [a for a in options if a.account_type.value == "BANK"]
        names = {b.casefold() for b in banks if b}
        if names:
            of_bank = [a.id for a in bank_accounts if any(n in f"{a.institution} {a.name}".casefold().split()
                                                          or n == (a.institution or "").casefold() for n in names)]
            return of_bank[0] if len(of_bank) == 1 else None  # another bank's card is never guessed as this one
        return bank_accounts[0].id if len(bank_accounts) == 1 else None

    def read(self, messages: list[tuple], cursor_ms: int | None = None) -> dict:
        """New messages (sender, text, received[, inbox ms]) into review. Returns counts: staged rows by account,
        waiting, skipped (not money, or read before). A pasted or shared message is known by its text; an inbox
        one (with its ms) by text and time, so two equal purchases are both read. Staging, what was seen and the
        inbox cursor commit together: a crash leaves nothing half-done to stage twice."""
        seen = self._json(SEEN_KEY, [])
        exact = set(seen)
        texts = {e for e in seen if "@" not in e}
        stamped = {e.split("@")[0] for e in seen if "@" in e}
        endings = self.endings()
        # The current SMS patterns read EGP amounts only. A saved mapping must never turn pounds into
        # dollars merely because a foreign account was selected (or an old mapping became unusable).
        usable = {a.id for a in self.accounts.list(active_only=True) if a.currency == "EGP"}
        endings = {ending: account_id for ending, account_id in endings.items() if account_id in usable}
        waiting = self._json(WAITING_KEY, [])
        by_account: dict[int, list[SmsTransaction]] = {}
        skipped = 0
        unread = self._json(UNREAD_KEY, [])
        banks = set(self._json(BANK_SENDERS_KEY, []))
        quiet = self.quiet_senders()
        for sender, text, received, *extra in messages:
            fp = fingerprint(text)
            mark = f"{fp}@{extra[0]}" if extra and extra[0] is not None else fp
            if (mark in exact or fp in texts) if mark != fp else (fp in texts or fp in stamped):
                skipped += 1
                continue
            exact.add(mark)
            (texts if mark == fp else stamped).add(fp)
            seen.append(mark)
            found = parse_sms(text, sender=sender, received=received)
            if found is not None:
                found = replace(found, text=" ".join(text.split())[:MAX_TEXT])
            if found is not None and sender:
                banks.add(sender[:40])
            if found is None:
                if looks_like_money(text) and sender[:40] not in quiet:  # kept for the owner to enter or dismiss
                    unread.append({"id": mark, "sender": sender[:40], "text": text[:MAX_TEXT],
                                   "received": received.isoformat(timespec="minutes")})
                else:
                    skipped += 1
                continue
            account_id = endings.get(found.ending)  # never guessed: the first message of an ending asks once
            if account_id is None:
                waiting.append(_to_json(found))
            else:
                by_account.setdefault(account_id, []).append(found)
        with self.db.transaction():
            transfers = self._pair_transfers(by_account, unread)
            staged = {account_id: self._stage(account_id, rows, transfers) for account_id, rows in by_account.items()
                      if rows}
            self.settings.set(SEEN_KEY, json.dumps(seen[-MAX_SEEN:]))
            self.settings.set(WAITING_KEY, json.dumps(waiting))
            self.settings.set(UNREAD_KEY, json.dumps(unread[-MAX_UNREAD:]))
            self.settings.set(BANK_SENDERS_KEY, json.dumps(sorted(banks)[:200]))
            if cursor_ms is not None:
                self.settings.set(LAST_READ_KEY, str(cursor_ms))
        return {"staged": staged, "waiting": len(waiting), "skipped": skipped, "unread": len(unread)}

    def read_source(self, source: SmsSource, now: datetime | None = None) -> dict | None:
        """New messages from the phone: shared ones, and the inbox since the last read when allowed (from
        OVERLAP_MS before the cursor, which only moves forward). Messages from phone numbers are people, never
        read. Returns `read`'s counts, or None when there was nothing."""
        now = now or datetime.now()
        messages = [("Shared", text, now) for text in source.take_shared() if text and text.strip()]
        newest = None
        if source.permission() == "granted":
            stored = self.settings.get(LAST_READ_KEY)
            after = int(stored) if stored.isdigit() else int((now - timedelta(days=FIRST_LOOK_DAYS)).timestamp() * 1000)
            for sender, body, received_ms in source.since(max(0, after - OVERLAP_MS) if stored.isdigit() else after):
                newest = max(newest or 0, int(received_ms))
                if not PERSON.match((sender or "").replace(" ", "")):
                    messages.append((sender or "", body or "", datetime.fromtimestamp(int(received_ms) / 1000),
                                     int(received_ms)))
            if newest is None and not stored.isdigit():
                newest = after  # the first look found nothing: start from there next time
            if newest is not None and stored.isdigit():
                newest = max(newest, after)  # never backwards
            if newest == after and stored.isdigit():
                newest = None  # unchanged
        if messages:
            return self.read(messages, newest)
        if newest is not None:
            with self.db.transaction():
                self.settings.set(LAST_READ_KEY, str(newest))
        return None

    def last_read(self) -> datetime | None:
        stored = self.settings.get(LAST_READ_KEY)
        return datetime.fromtimestamp(int(stored) / 1000) if stored.isdigit() else None

    def pending(self) -> tuple[int, int]:
        """(messages waiting for their account, messages no rule could read), in one query, for Needs you."""
        rows = {row[0]: row[1] for row in self.db.all("SELECT key, value FROM settings WHERE key IN (?, ?)",
                                                      (WAITING_KEY, UNREAD_KEY))}
        counts = []
        for key in (WAITING_KEY, UNREAD_KEY):
            try:
                value = json.loads(rows.get(key) or "[]")
            except ValueError:
                value = []
            counts.append(len(value) if isinstance(value, list) else 0)
        return counts[0], counts[1]

    def quiet_senders(self) -> set[str]:
        """Senders whose unreadable messages are not shown any more: the owner dismissed QUIET_AFTER of them and the
        sender never sent a message a rule read (a bank's sender is never quieted)."""
        banks = set(self._json(BANK_SENDERS_KEY, []))
        return {sender for sender, count in self._json(QUIET_KEY, {}).items()
                if count >= QUIET_AFTER and sender not in banks}

    def unread(self) -> list[dict]:
        """Messages with an amount that no rule could read, newest first. An offer kept before the offer filter
        (2026-11-01), or a message from a sender quieted since, is left out."""
        quiet = self.quiet_senders()
        return [m for m in reversed(self._json(UNREAD_KEY, []))
                if m.get("reason") or (m.get("sender", "") not in quiet and not is_offer(m.get("text", "")))]

    def dismiss(self, message_id: str) -> None:
        """Remove a kept message. Its sender counts towards being quieted, unless it is a bank's. ``balance:<account id>``
        quiets that account's balance check instead (NF-7AP)."""
        if message_id.startswith("balance:") and message_id[8:].isdigit():
            return self._dismiss_balance(int(message_id[8:]))
        kept = self._json(UNREAD_KEY, [])
        gone = next((m for m in kept if m.get("id") == message_id), None)
        counts = self._json(QUIET_KEY, {})
        sender = "" if gone is None or gone.get("reason") else gone.get("sender", "")  # a held transfer half: a bank's
        if sender:
            counts[sender] = counts.get(sender, 0) + 1
        with self.db.transaction():
            self.settings.set(UNREAD_KEY, json.dumps([m for m in kept if m.get("id") != message_id]))
            if sender:
                self.settings.set(QUIET_KEY, json.dumps(dict(sorted(counts.items(), key=lambda kv: -kv[1])[:200])))

    def assign(self, ending: str, account_id: int) -> int | None:
        """The owner says which account an ending is: remember it and send its waiting messages to review."""
        return self.assign_many({ending: account_id}).get(ending)

    def assign_many(self, answers: dict[str, int]) -> dict[str, int]:
        """Several endings answered at once (From SMS asks them together): remember each and send their waiting
        messages to review, one batch per account. Returns {ending: batch id} for endings that had messages."""
        accounts = {}
        for ending, account_id in answers.items():
            if not (re.fullmatch(r"\d{4}", ending) or ending == SALARY_ENDING):
                raise ValidationError("Choose the account for these messages.", "ending")
            account = self.accounts.require_usable(account_id)
            if account.currency != "EGP":
                raise ValidationError("Bank SMS are in EGP. Choose an EGP account.", "account_id")
            accounts[ending] = account
        # Account codes are unique and survive checkpoint replication, unlike SQLite row ids.
        # Accept old id-valued settings and normalize every mapping as soon as it is edited.
        saved = self._json(ENDINGS_KEY, {})
        endings = {}
        for old_ending, old_value in saved.items():
            old_text = str(old_value)
            old_id = int(old_text) if old_text.isdigit() else self.db.scalar(
                "SELECT id FROM accounts WHERE code=?", (old_text,))
            code = self.db.scalar("SELECT code FROM accounts WHERE id=?", (old_id,)) if old_id is not None else None
            if code:
                endings[str(old_ending)] = code
        for ending, account in accounts.items():
            endings[ending] = account.code
        waiting = self._json(WAITING_KEY, [])
        rows: dict[int, list[SmsTransaction]] = {}
        for item in waiting:
            if item["ending"] in accounts:
                rows.setdefault(int(accounts[item["ending"]].id), []).append(_from_json(item))
        rest = [item for item in waiting if item["ending"] not in accounts]
        with self.db.transaction():  # staging and leaving the waiting list commit together
            batches = {account_id: self._stage(account_id, mine) for account_id, mine in rows.items()}
            self.settings.set(ENDINGS_KEY, json.dumps(endings))
            self.settings.set(WAITING_KEY, json.dumps(rest))
        return {ending: batches[int(account.id)] for ending, account in accounts.items() if int(account.id) in batches}

    def _cash_account_name(self) -> str:
        """Where an ATM withdrawal's cash went: the one cash-at-hand wallet, else the only wallet, else the wallet
        that took most money from your bank accounts in the last year. Empty when nothing says (the review asks)."""
        cash = [a for a in self.accounts.list(active_only=True)
                if a.account_type.value == "CASH" and a.currency == "EGP"]
        at_hand = [a for a in cash if a.cash_at_hand]
        if len(at_hand) == 1 or len(cash) == 1:
            return (at_hand or cash)[0].name
        if not cash:
            return ""
        ids = {a.id: a.name for a in cash}
        since = (today() - timedelta(days=365)).isoformat()
        marks = ",".join("?" * len(ids))
        row = self.db.one(
            "SELECT inn.account_id, COUNT(*) AS n FROM ledger_entries inn "
            "JOIN transactions t ON t.id = inn.transaction_id "
            "JOIN ledger_entries out ON out.transaction_id = t.id AND out.amount_e6 < 0 "
            "JOIN accounts b ON b.id = out.account_id AND b.account_type = 'BANK' "
            f"WHERE t.type = 'TRF' AND t.status = 'POSTED' AND t.date >= ? AND inn.amount_e6 > 0 "
            f"AND inn.account_id IN ({marks}) GROUP BY inn.account_id ORDER BY n DESC, inn.account_id LIMIT 1",
            (since, *ids))
        return ids.get(int(row[0]), "") if row else ""

    def _pair_transfers(self, by_account: dict[int, list[SmsTransaction]], held: list[dict]) -> dict[int, str]:
        """Money that left one of your accounts and arrived in another (two banks, two messages, one transfer):
        the sending row becomes a transfer to the other account, and the arriving message is held on From SMS
        as its other side, so it is never posted twice and never dropped unseen. Same amount, at most
        PAIR_MINUTES apart. Returns {id(sending row): receiving account's name}."""
        names = {a.id: a.name for a in self.accounts.list(active_only=True)}
        arrivals = [(account_id, row) for account_id, rows in by_account.items() for row in rows
                    if row.kind in ("transfer_in", "money_in")]
        paired: dict[int, str] = {}
        for account_id, rows in by_account.items():
            for row in rows:
                if row.kind not in ("transfer_out", "money_out"):
                    continue
                sent = datetime.fromisoformat(row.when)
                match = next(((other_id, other) for other_id, other in arrivals
                              if other_id != account_id and other.amount == row.amount and other_id in names
                              and abs((datetime.fromisoformat(other.when) - sent).total_seconds()) <= PAIR_MINUTES * 60),
                             None)
                if match is None:
                    continue
                other_id, other = match
                arrivals.remove(match)
                by_account[other_id].remove(other)
                paired[id(row)] = names[other_id]
                held.append({"id": fingerprint(f"pair {other.ending} {other.amount} {other.when} {other.reference}"),
                             "sender": other.bank, "received": other.when,
                             "text": f"{KIND_NOTES[other.kind]} {format(other.amount, 'f')} into …{other.ending}"
                                     + (f" from {other.place}" if other.place else ""),
                             "reason": f"Held as the other side of the transfer from {names.get(account_id, '')}. "
                                       "Dismiss it once that transfer is posted; enter it only if it was not one."})
        return paired

    def _note_balance(self, account_id: int, rows: list[SmsTransaction]) -> None:
        """Keep the newest balance a message states for the account (NF-7AP). A card's available limit is not a balance."""
        stated = [r for r in rows if r.balance is not None and not _CARD_LIMIT.search(getattr(r, "text", "") or "")]
        if not stated:
            return
        newest = max(stated, key=lambda r: r.when)
        notes = self._json(BALANCES_KEY, {})
        old = notes.get(str(account_id))
        if old and old["date"] > newest.when[:10]:
            return
        notes[str(account_id)] = {"balance": format(newest.balance, "f"), "date": newest.when[:10], "dismissed": False}
        self.settings.set(BALANCES_KEY, json.dumps(notes))

    def stated_balances(self) -> dict[int, dict]:
        """{account_id: {"balance", "date", "dismissed"}}: what the bank last said, to compare with the ledger."""
        return {int(k): v for k, v in self._json(BALANCES_KEY, {}).items() if str(k).isdigit()}

    def _dismiss_balance(self, account_id: int) -> None:
        """A pending hold makes the bank's figure lag: the row stays quiet until a later message states a balance."""
        notes = self._json(BALANCES_KEY, {})
        if str(account_id) in notes:
            notes[str(account_id)]["dismissed"] = True
            self.settings.set(BALANCES_KEY, json.dumps(notes))

    def _stage(self, account_id: int, rows: list[SmsTransaction], transfers: dict[int, str] | None = None) -> int:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Date", "Amount", "Counterparty", "Category", "Notes", "Reference", "Message"])
        cash = self._cash_account_name()
        for row in sorted(rows, key=lambda r: r.when):
            notes = KIND_NOTES[row.kind] + (f" · {row.place}" if row.place and row.kind != "salary" else "")
            if not row.sure:
                notes = "Check this: read by the general rule · " + notes
            category, counterparty = "", row.place if row.kind in ("purchase", "transfer_in", "money_out", "money_in") else ""
            if row.kind == "withdrawal":
                category = "Transfer"
                notes += f" · transfer to {cash}" if cash else ""
            elif transfers and id(row) in transfers:  # both sides came by SMS: one transfer, posted once
                category, counterparty = "Transfer", ""
                notes += f" · transfer to {transfers[id(row)]}"
            elif row.kind == "salary":
                category = "Salary"
            writer.writerow([row.when[:10], format(row.signed, "f"), counterparty, category, notes, row.reference, row.text])
        self._note_balance(account_id, rows)
        batch_id, _ = self.bank_imports.stage(account_id, f"SMS {datetime.now():%Y-%m-%d %H:%M}",
                                              out.getvalue().encode("utf-8"))
        return batch_id


def _to_json(found: SmsTransaction) -> dict:
    data = asdict(found)
    data["amount"] = format(found.amount, "f")
    data["balance"] = format(found.balance, "f") if found.balance is not None else None
    return data


def _from_json(data: dict) -> SmsTransaction:
    return SmsTransaction(**(data | {"amount": Decimal(data["amount"]),
                                     "balance": Decimal(data["balance"]) if data.get("balance") else None}))
