"""Reading a bank statement row (IT-9K): the column names, the CSV decoder, and the date and amount readers that
turn what a bank prints into what the review shows. Pure functions, no database; `bank_imports` and the journal's
capture both read rows through here. Moved unchanged out of `bank_imports`, which still exports every name."""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation

from lightning.core.dates import today
from lightning.import_profile import read_date
from lightning.core.errors import ValidationError
from lightning.core.limits import MAX_CSV_IMPORT_BYTES
from lightning.core.money import ascii_digits

REQUIRED = ("Date", "Amount")
# "Group" is the parent a category sits under in another app's export ("Work" for "Work › Transportation").
# "Direction" is a column whose values say money in or out, beside an unsigned Amount (DR/CR, Income/Expense; IT-7AA2).
OPTIONAL = ("Counterparty", "Category", "Group", "Notes", "Reference", "Direction", "Currency", "Account", "Balance", "Subcategory", "Split")
SEPARATE_AMOUNT_FIELDS = ("Inflow", "Outflow")
MAX_BYTES = MAX_CSV_IMPORT_BYTES

# What each column is usually called, in English and Arabic (IT-7AA5): the column step's suggestion and the finder
# of the header row below a preamble both read this one table.
HEADER_ALIASES = {
    "Date": ("date", "transaction date", "posting date", "booking date", "value date", "التاريخ", "تاريخ", "تاريخ العملية"),
    "Amount": ("amount", "transaction amount", "net amount", "value", "المبلغ", "القيمة"),
    "Inflow": ("inflow", "money in", "credit", "credits", "deposit", "deposits", "دائن", "إيداع", "ايداع", "وارد"),
    "Outflow": ("outflow", "money out", "debit", "debits", "withdrawal", "withdrawals", "مدين", "سحب", "صادر"),
    "Counterparty": ("counterparty", "merchant", "payee", "beneficiary", "party", "name", "المستفيد", "الطرف", "الاسم"),
    "Category": ("category", "الفئة", "التصنيف"),
    "Subcategory": ("subcategory", "sub category", "sub-category", "الفئة الفرعية"),
    "Split": ("split amount", "split", "split_amount", "part amount", "جزء"),
    "Direction": ("direction", "dr cr", "cr dr", "debit credit", "credit debit", "in out", "income expense",
                  "expense income", "transaction type", "type of transaction", "dr or cr", "debit or credit",
                  "نوع العملية"),
    "Group": ("category group", "group", "parent category", "main category", "master category", "category parent"),
    "Currency": ("currency", "currency code", "ccy", "cur", "العملة"),
    "Account": ("account", "account name", "wallet", "from account", "الحساب"),
    "Notes": ("notes", "memo", "narrative", "details", "description", "البيان", "الوصف", "التفاصيل", "ملاحظات"),
    "Reference": ("reference", "ref", "transaction id", "transaction reference", "المرجع", "رقم المرجع"),
    "Balance": ("balance", "running balance", "available balance", "closing balance", "الرصيد"),
}


def normalize_header(header: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in header).split())


_PATH = re.compile(r"\s*(?:›|»|>|:|\\|\|)\s*|\s+/\s+|(?<=\w)/(?=\w)")


def split_category_path(text: str) -> tuple[str, str]:
    """"Personal:Food", "Work > Transportation", "Food/Groceries" as (group, name); ("", text) when it is no path."""
    parts = [p.strip() for p in _PATH.split(text or "") if p.strip()]
    return (parts[-2], parts[-1]) if len(parts) >= 2 else ("", (text or "").strip())


def _is_header_row(cells) -> bool:
    known = {name for names in HEADER_ALIASES.values() for name in names}
    return sum(normalize_header(c) in known for c in cells) >= 2


CSV_ENCODINGS = {"auto", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1256", "cp1252"}


def _decode_text(data: bytes, encoding: str = "auto") -> str:
    """Strict decoding: explicit legacy encodings resolve the Arabic/Western ambiguity."""
    if encoding not in CSV_ENCODINGS:
        raise ValidationError("Choose a supported CSV encoding.", "encoding")
    candidates = [encoding]
    if encoding == "auto":
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            candidates = ["utf-16"]
        elif b"\x00" in data[:512]:
            sample = data[:512]
            candidates = ["utf-16-le" if sample[1::2].count(0) > sample[::2].count(0) else "utf-16-be"]
        else:
            candidates = ["utf-8-sig", "cp1256"]
    for codec in candidates:
        try:
            text = data.decode(codec).lstrip("\ufeff")
            if "\x00" not in text:
                return text
        except UnicodeDecodeError:
            continue
    raise ValidationError("This CSV could not be decoded. Choose its encoding and upload it again.", "encoding")


def normalize_csv_encoding(data: bytes, encoding: str = "auto") -> bytes:
    if len(data) > MAX_BYTES:
        raise ValidationError("CSV files must be 5 MB or smaller.", "file")
    if encoding in {"auto", "utf-8-sig"} and b"\x00" not in data:
        try:
            data.decode("utf-8-sig")
            return data  # keep historical file hashes stable for ordinary UTF-8 uploads
        except UnicodeDecodeError:
            pass
    normalized = _decode_text(data, encoding).encode("utf-8")
    if len(normalized) > MAX_BYTES:
        raise ValidationError("CSV files must be 5 MB or smaller.", "file")
    return normalized


def _header_line(text: str) -> int:
    """Index of the first line that reads as a header row (two or more known column names); 0 when none does, so a
    file with its own odd names keeps working as before. Preamble lines above it are the bank's, not rows."""
    for index, line in enumerate(text.splitlines()[:40]):
        for delimiter in (",", ";", "\t"):
            if _is_header_row(next(csv.reader([line], delimiter=delimiter), [])):
                return index
    return 0


INTERNAL_WORDS = {"internal", "internal transfer", "transfer", "transfers", "own account"}


# Rows another app wrote to set or correct its own balance. Lightning keeps the account's opening balance and its
# reconciliations itself, so posting these would count the money twice (owner feedback, 2026-11-05).
BALANCE_WORDS = {"starting balance", "starting balances", "opening balance", "opening balances", "initial balance",
                 "balance adjustment", "balance adjustments", "adjustment", "adjustments", "balance correction",
                 "reconciliation", "reconciliation adjustment"}


_BANK_PREFIX = re.compile(
    r"^(?:CARD PURCHASE|POS PURCHASE|DEBIT CARD PURCHASE|ONLINE PURCHASE|ONLINE PAYMENT|PURCHASE|POS|DEBIT CARD|"
    r"VISA|MASTERCARD|PAYMENT TO|PAYMENT|INSTAPAY TO|INSTAPAY|TRANSFER TO|TRANSFER FROM|FAWRY)\b[\s\-:*/]*", re.I)
_PLACE_WORDS = {"EG", "EGY", "EGYPT", "CAIRO", "GIZA", "ALEXANDRIA", "ALEX", "CAI", "GBR", "USA", "US", "LTD", "LLC"}


def clean_merchant(description: str) -> str:
    """"CARD PURCHASE TALABAT" and "UBER *TRIP HELP.UBER.COM" as "Talabat" and "Uber": the merchant, not the bank's
    wording, reference numbers or city (IT-7AA4). "" when nothing is left to name (an ATM withdrawal)."""
    text = " ".join((description or "").split())
    previous = None
    while text != previous:  # "POS PURCHASE VISA ..." drops each prefix in turn
        previous, text = text, _BANK_PREFIX.sub("", text, count=1)
    text = re.split(r"[*#]|\s-\s|https?:|www\.", text, maxsplit=1)[0]
    words = []
    for word in text.split():
        bare = word.strip(".,;:")
        if not bare or re.fullmatch(r"[\d/\-.:]+", bare) or sum(ch.isdigit() for ch in bare) >= 4 or "." in bare and bare[-3:].isalpha():
            if words:
                break
            continue
        if bare.upper() in _PLACE_WORDS and words:
            break
        words.append(bare)
    name = " ".join(words[:3]).strip()
    if not name or name.upper() in {"ATM", "ATM WITHDRAWAL", "WITHDRAWAL", "CASH", "FEE", "FEES"}:
        return ""
    return name.title() if name.isascii() and not any(ch.islower() for ch in name) else name


def is_balance_row(*texts: str) -> bool:
    """The Category or Counterparty says the row is another app's opening balance or balance adjustment."""
    return any(" ".join((text or "").split()).casefold() in BALANCE_WORDS for text in texts)


class SkipRow(ValueError):
    """A row that is clearly not a transaction (IT-7AA6): it opens as a skipped row with this reason, not an error."""


TOTAL_WORDS = ("total", "totals", "closing balance", "opening balance", "balance carried", "balance brought",
               "summary", "grand total", "الإجمالي", "اجمالي", "إجمالي", "الرصيد الختامي", "الرصيد الافتتاحي")


def is_total_line(*texts: str) -> bool:
    """A footer such as ",Total,14749.50": no date, and a cell that says total or balance."""
    return any(" ".join((t or "").split()).casefold().strip(":") in TOTAL_WORDS for t in texts)


def is_internal(category: str) -> bool:
    """The Category column says the row moved money between your own accounts."""
    return " ".join((category or "").split()).casefold() in INTERNAL_WORDS


def _date(value: str, profile=None) -> str:
    try:
        day = read_date(value, profile)
    except ValidationError as exc:
        raise ValueError(exc.message) from None
    if day > today():  # the same rule as typing it: the review marks the row to fix at once, not when Post fails
        raise SkipRow(f"{day.isoformat()} is in the future, so this looks like a pending hold: skipped until it posts. Import it again later.")
    return day.isoformat()


def _decimal_amount(value: str) -> Decimal:
    try:
        text = ascii_digits((value or "").strip())
        text = text.replace("−", "-").replace("–", "-").replace(" ", "")
        if not text:
            return Decimal("0")
        # Strip a recognized currency wrapper, never arbitrary non-digit text: stripping
        # punctuation would turn .50 into 50 and silently accept values such as 5%.
        currency = r"(?:EGP|USD|EUR|GBP|LE|E£|ج\.?م\.?|[$€£])"
        wrappers = 0

        def strip_currency(text):
            nonlocal wrappers
            text, count = re.subn(rf"^{currency}|{currency}$", "", text, flags=re.IGNORECASE)
            wrappers += count
            if wrappers > 1:
                raise ValueError("Enter a valid number.")
            return text

        text = strip_currency(text)
        negative = False
        if text.startswith("(") and text.endswith(")") and len(text) > 2:
            negative = True
            text = text[1:-1]
        elif text.endswith("-") and len(text) > 1:
            negative = True
            text = text[:-1]
        elif text.startswith(("-", "+")) and len(text) > 1:
            negative = text[0] == "-"
            text = text[1:]
        text = strip_currency(text)
        if not text or "-" in text or "(" in text or ")" in text:
            raise ValueError("Enter a valid number.")
        if not re.fullmatch(r"(?:[0-9][0-9.,]*|[.,][0-9]+)", text):
            raise ValueError("Enter a valid number.")
        if "," in text and ("." not in text or text.rfind(",") > text.rfind(".")):
            tail = text.rsplit(",", 1)[1]
            text = text.replace(".", "").replace(",", ".") if len(tail) == 2 else text.replace(",", "")
        else:
            text = text.replace(",", "")
        amount = Decimal(text)
        if not amount.is_finite():
            raise InvalidOperation
        return -amount if negative else amount
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid number.") from None


def _amount(value: str) -> str:
    amount = _decimal_amount(value)
    if amount == 0:
        raise SkipRow("A zero amount records nothing, so this row is skipped.")
    return format(amount, "f")


MONEY_OUT_WORDS = {"dr", "d", "debit", "debits", "out", "outflow", "expense", "expenses", "withdrawal", "payment",
                   "paid", "spent", "مدين", "سحب", "مصروف", "مصروفات", "صرف"}
MONEY_IN_WORDS = {"cr", "c", "credit", "credits", "in", "inflow", "income", "deposit", "received", "refund",
                  "دائن", "ايداع", "إيداع", "دخل", "إيراد", "ايراد"}


def direction_sign(value: str) -> int:
    """-1 for money out, +1 for money in, from a Direction column's value; anything else is an error to fix."""
    word = " ".join(re.sub(r"[^\w ]", " ", value or "").split()).casefold()
    if word in MONEY_OUT_WORDS:
        return -1
    if word in MONEY_IN_WORDS:
        return 1
    raise ValueError(f"“{value}” in the Direction column is not money in or out. Use DR/CR, Debit/Credit or Income/Expense.")


_CURRENCY_NAMES = {"le": "EGP", "l.e": "EGP", "l.e.": "EGP", "جنيه": "EGP", "جنيه مصري": "EGP", "ج.م": "EGP",
                   "egp": "EGP", "$": "USD", "us$": "USD", "دولار": "USD", "€": "EUR", "£": "GBP"}


def currency_code(value: str) -> str:
    """A Currency cell as an ISO code (EGP for LE and Arabic names); "" when the cell is empty."""
    text = " ".join((value or "").split())
    return _CURRENCY_NAMES.get(text.casefold(), text.upper())


def _separate_amount(inflow: str, outflow: str) -> str:
    incoming, outgoing = _decimal_amount(inflow), _decimal_amount(outflow)
    if incoming and outgoing:
        raise ValueError("A row cannot have both an inflow and an outflow amount.")
    if not incoming and not outgoing:
        raise ValueError("Enter an amount in either the inflow or outflow column.")
    signed = abs(incoming) if incoming else -abs(outgoing)
    return format(signed, "f")


def decode_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(data) > MAX_BYTES:
        raise ValidationError("CSV files must be 5 MB or smaller.", "file")
    text = _decode_text(data)
    skipped = _header_line(text)
    if skipped:
        text = "\n".join(text.splitlines()[skipped:]) + "\n"
    try:
        sample = text[:4096]
        try:
            options = {"dialect": csv.Sniffer().sniff(sample, delimiters=",;\t")} if sample else {}
        except csv.Error:
            # A sample ending inside a quoted multiline field can defeat Sniffer.
            # Accept only a unique delimiter that parses the entire file consistently.
            candidates = []
            for delimiter in (",", ";", "\t"):
                try:
                    records = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
                    header = next(records, [])
                    if len(header) > 1 and all(not row or len(row) == len(header) for row in records):
                        candidates.append(delimiter)
                except csv.Error:
                    continue
            if len(candidates) != 1:
                raise
            options = {"delimiter": candidates[0]}
        reader = csv.DictReader(io.StringIO(text, newline=""), **options)
        headers = [str(h or "").strip() for h in (reader.fieldnames or [])]
        if not headers or any(not h for h in headers):
            raise ValidationError("The CSV needs a header row with column names.", "file")
        if len(set(headers)) != len(headers):
            raise ValidationError("CSV headers must be unique; rename duplicate columns and try again.", "file")
        rows = []
        for line, row in enumerate(reader, start=2 + skipped):
            rows.append({h: str(row.get(h, "") or "").strip() for h in headers} | {"__line__": str(line)})
        return headers, rows
    except csv.Error as exc:
        raise ValidationError(f"Could not read this CSV: {exc}", "file") from None
