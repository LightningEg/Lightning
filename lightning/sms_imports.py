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
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

from lightning.core.errors import ValidationError

ENDINGS_KEY = "sms_account_endings"   # {"0285": account_id}
SEEN_KEY = "sms_seen"                  # messages already read, newest last: "fp" (text only) or "fp@ms" (inbox)
WAITING_KEY = "sms_waiting"            # parsed messages whose account ending is not known yet
UNREAD_KEY = "sms_unread"              # messages with an amount that no rule could read: never dropped unseen
LAST_READ_KEY = "sms_last_read_ms"     # the phone's inbox is read from here on
MAX_UNREAD = 200
OVERLAP_MS = 10 * 60 * 1000            # the inbox is re-read this far before the cursor: late arrivals are not lost
PAIR_MINUTES = 30                      # an own transfer's two messages arrive within this
FIRST_LOOK_DAYS = 30                   # the first read goes this far back
PERSON = re.compile(r"^\+?\d{7,}$")     # a phone number: a person, not a bank's sender name or short code
SALARY_ENDING = "salary"               # the salary message names no account: its own remembered choice
MAX_SEEN = 5000
MAX_TEXT = 1000

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
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


_OUT_WORDS = r"(خصم|سحب|شراء|سداد|دفع|مدفوعات|تحويل\s*لحظي\s*من|تحويل\s*من\s*حساب|debited|withdraw\w*|purchase|paid|spent|sent)"
_IN_WORDS = r"(إضافة|اضافة|إيداع|ايداع|استلام|استرداد|لحسابكم|إلى\s*حسابك|الى\s*حسابك|credited|received|deposit\w*|refund\w*)"


def looks_like_money(text: str) -> bool:
    """An amount with a currency: a message the owner should see even when no rule reads it."""
    flat = _clean(text or "")
    return bool(re.search(_CUR + r"\s*" + _NUM + r"|" + _NUM + r"\s*" + _CUR, flat)) and not _IGNORE.search(flat)


def _general(flat: str, received: datetime, balance: Decimal | None, bank: str) -> SmsTransaction | None:
    """The general rule, for a wording no bank pattern knows yet: an amount with its currency, an account or
    card ending, and words that say which way the money went. All three, or nothing."""
    money = re.search(_CUR + r"\s*" + _NUM + r"|" + _NUM + r"\s*" + _CUR, flat)
    ending = re.search(r"(?:رقم|المنتهي\S*\s*ب[ـ]?|ending(?:\s*(?:with|in))?|[*xX•]{2,})\s*[*xX•]*\s*(\d{4})\b", flat,
                       re.IGNORECASE)
    out_word = re.search(_OUT_WORDS, flat, re.IGNORECASE)
    in_word = re.search(_IN_WORDS, flat, re.IGNORECASE)
    if not money or not ending or bool(out_word) == bool(in_word):
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

    def waiting(self) -> list[dict]:
        """Messages read whose account is not known yet, grouped by ending: [{"ending", "count", "total"}]."""
        groups: dict[str, dict] = {}
        for item in self._json(WAITING_KEY, []):
            group = groups.setdefault(item["ending"], {"ending": item["ending"], "count": 0, "kinds": set()})
            group["count"] += 1
            group["kinds"].add(item["kind"])
        return [dict(g, kinds=sorted(g["kinds"])) for g in groups.values()]

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
            if found is None:
                if looks_like_money(text):  # never dropped unseen: kept for the owner to enter or dismiss
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

    def unread(self) -> list[dict]:
        """Messages with an amount that no rule could read, newest first."""
        return list(reversed(self._json(UNREAD_KEY, [])))

    def dismiss(self, message_id: str) -> None:
        with self.db.transaction():
            self.settings.set(UNREAD_KEY, json.dumps([m for m in self._json(UNREAD_KEY, [])
                                                      if m.get("id") != message_id]))

    def assign(self, ending: str, account_id: int) -> int | None:
        """The owner says which account an ending is: remember it and send its waiting messages to review."""
        if not (re.fullmatch(r"\d{4}", ending) or ending == SALARY_ENDING):
            raise ValidationError("Choose the account for these messages.", "ending")
        account = self.accounts.require_usable(account_id)
        if account.currency != "EGP":
            raise ValidationError("Bank SMS are in EGP. Choose an EGP account.", "account_id")
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
        endings[ending] = account.code
        waiting = self._json(WAITING_KEY, [])
        mine = [_from_json(item) for item in waiting if item["ending"] == ending]
        rest = [item for item in waiting if item["ending"] != ending]
        with self.db.transaction():  # staging and leaving the waiting list commit together
            batch = self._stage(int(account.id), mine) if mine else None
            self.settings.set(ENDINGS_KEY, json.dumps(endings))
            self.settings.set(WAITING_KEY, json.dumps(rest))
        return batch

    def _cash_account_name(self) -> str:
        cash = [a for a in self.accounts.list(active_only=True)
                if a.account_type.value == "CASH" and a.currency == "EGP"]
        return cash[0].name if len(cash) == 1 else ""

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

    def _stage(self, account_id: int, rows: list[SmsTransaction], transfers: dict[int, str] | None = None) -> int:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Date", "Amount", "Counterparty", "Category", "Notes", "Reference"])
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
            writer.writerow([row.when[:10], format(row.signed, "f"), counterparty, category, notes, row.reference])
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
