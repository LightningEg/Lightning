"""Reading a bank statement row (IT-9K): the column names, the CSV decoder, and the date and amount readers that
turn what a bank prints into what the review shows. Pure functions, no database; `bank_imports` and the journal's
capture both read rows through here. Moved unchanged out of `bank_imports`, which still exports every name."""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation

from lightning.core.dates import parse_date, today
from lightning.core.errors import ValidationError
from lightning.core.limits import MAX_CSV_IMPORT_BYTES
from lightning.core.money import ascii_digits

REQUIRED = ("Date", "Amount")
OPTIONAL = ("Counterparty", "Category", "Notes", "Reference")
SEPARATE_AMOUNT_FIELDS = ("Inflow", "Outflow")
# A column that says which way a positive amount went (7Z): DR/CR, D/C, Debit/Credit, مدين/دائن.
DIRECTION_FIELD = "Direction"
DEBIT_MARKS = {"dr", "d", "db", "debit", "debit.", "withdrawal", "out", "مدين", "سحب", "خصم"}
CREDIT_MARKS = {"cr", "c", "credit", "credit.", "deposit", "in", "دائن", "إيداع", "ايداع", "اضافة", "إضافة"}
MAX_BYTES = MAX_CSV_IMPORT_BYTES

# Column names a bank may print for each field, as `header_key` reads them (lower case, Arabic letters folded).
# Shared by the map step's suggestions and by finding the header row under a bank's title lines (7AA).
HEADER_ALIASES = {
    "Date": ("date", "transaction date", "txn date", "trans date", "posting date", "post date", "booking date",
             "value date", "تاريخ", "التاريخ", "تاريخ الحركه", "تاريخ العمليه", "تاريخ القيد", "تاريخ المعامله",
             "تاريخ الحركة", "تاريخ العملية"),
    "Amount": ("amount", "transaction amount", "net amount", "value", "amount egp", "المبلغ", "مبلغ", "القيمه"),
    "Inflow": ("inflow", "money in", "credit", "credits", "deposit", "deposits", "credit amount", "paid in",
               "دائن", "الدائن", "ايداع", "ايداعات", "اضافه"),
    "Outflow": ("outflow", "money out", "debit", "debits", "withdrawal", "withdrawals", "debit amount", "paid out",
                "مدين", "المدين", "سحب", "مسحوبات", "خصم"),
    "Counterparty": ("counterparty", "merchant", "merchant name", "payee", "beneficiary", "beneficiary name", "party",
                     "name", "المستفيد", "الجهه", "التاجر"),
    "Category": ("category", "type", "التصنيف", "الفئه"),
    "Notes": ("notes", "memo", "narrative", "narration", "particulars", "details", "transaction details", "description",
              "البيان", "الوصف", "التفاصيل", "الشرح", "ملاحظات"),
    "Reference": ("reference", "ref", "ref no", "reference number", "transaction id", "transaction reference",
                  "المرجع", "رقم المرجع", "رقم العمليه"),
}
_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": None})
SUMMARY_WORDS = ("total", "totals", "subtotal", "sub total", "opening balance", "closing balance", "balance brought",
                 "balance carried", "brought forward", "carried forward", "اجمالي", "الاجمالي", "المجموع", "رصيد",
                 "الرصيد")
_DATE_LIKE = re.compile(r"\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}")


def header_key(text: str) -> str:
    """A column name as the aliases spell it: lower case, punctuation to spaces, Arabic letter forms folded."""
    folded = (text or "").translate(_ARABIC_FOLD)
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in folded).split())


INTERNAL_WORDS = {"internal", "internal transfer", "transfer", "transfers", "own account"}


def is_internal(category: str) -> bool:
    """The Category column says the row moved money between your own accounts."""
    return " ".join((category or "").split()).casefold() in INTERNAL_WORDS


def _date(value: str) -> str:
    try:
        day = parse_date(value)
    except ValidationError as exc:
        raise ValueError(exc.message) from None
    if day > today():  # the same rule as typing it: the review marks the row to fix at once, not when Post fails
        raise ValueError(f"{day.isoformat()} is in the future. Record transactions on or after the day they happen.")
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


def _direction(value: str) -> int:
    """-1 for a debit marker, +1 for a credit marker; anything else is a row to fix, never a guess."""
    mark = " ".join((value or "").split()).casefold().strip(".")
    if mark in DEBIT_MARKS or mark + "." in DEBIT_MARKS:
        return -1
    if mark in CREDIT_MARKS or mark + "." in CREDIT_MARKS:
        return 1
    raise ValueError(f"The debit/credit column says \"{value or 'nothing'}\": use DR or CR (مدين or دائن).")


def looks_like_direction(values) -> bool:
    """Every filled cell of the column is a debit or credit marker, and there is at least one."""
    filled = [v for v in values if (v or "").strip()]
    if not filled:
        return False
    try:
        return all(_direction(v) for v in filled)
    except ValueError:
        return False


def _amount(value: str) -> str:
    amount = _decimal_amount(value)
    if amount == 0:
        raise ValueError("Enter a non-zero amount; use a minus sign for money out.")
    return format(amount, "f")


def _separate_amount(inflow: str, outflow: str) -> str:
    incoming, outgoing = _decimal_amount(inflow), _decimal_amount(outflow)
    if incoming and outgoing:
        raise ValueError("A row cannot have both an inflow and an outflow amount.")
    if not incoming and not outgoing:
        raise ValueError("Enter an amount in either the inflow or outflow column.")
    signed = abs(incoming) if incoming else -abs(outgoing)
    return format(signed, "f")


def _decode_text(data: bytes) -> str:
    """UTF-8 first; UTF-16 when the file says so (Excel's "Unicode text"); else Windows Arabic (cp1256), which is what
    Excel saves as "CSV" on an Arabic Windows. cp1256 reads any byte, so it is last."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("cp1256")
    except UnicodeDecodeError:
        raise ValidationError("Save the statement as a UTF-8 CSV file.", "file") from None


def _header_line(lines: list[str]) -> int:
    """The line that names the columns: the first of the first 30 with a date column and an amount column. Banks put
    their name, the account number and the period above it. When none qualifies, the first line is the header."""
    return header_row_index([max((next(csv.reader([line], delimiter=d), []) for d in ",;\t"), key=len)
                             for line in lines[:30]])


def header_row_index(rows: list[list[str]]) -> int:
    """Of rows of cells, the first of the first 30 with a date column and an amount column; else 0."""
    dates, amounts = set(HEADER_ALIASES["Date"]), {*HEADER_ALIASES["Amount"], *HEADER_ALIASES["Inflow"],
                                                   *HEADER_ALIASES["Outflow"]}
    for index, cells in enumerate(rows[:30]):
        keys = {header_key(str(cell)) for cell in cells}
        if keys & dates and keys & amounts:
            return index
    return 0


def _summary_row(values: list[str]) -> bool:
    """An empty line, or a total or balance line with no date in it: what a bank prints, not a transaction."""
    filled = [v for v in values if v]
    if not filled:
        return True
    if any(_DATE_LIKE.search(v) for v in filled):
        return False
    return any(header_key(v).startswith(SUMMARY_WORDS) for v in filled)


def decode_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(data) > MAX_BYTES:
        raise ValidationError("CSV files must be 5 MB or smaller.", "file")
    text = _decode_text(data)
    lines = text.splitlines(keepends=True)
    skipped = _header_line(lines)
    if skipped:
        text = "".join(lines[skipped:])
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
        reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
        headers = [str(h or "").strip() for h in (reader.fieldnames or [])]
        while skipped and headers and not headers[-1]:  # a title block's wider rows leave empty trailing names
            headers.pop()
        if not headers or any(not h for h in headers):
            raise ValidationError("The CSV needs a header row with column names.", "file")
        if len(set(headers)) != len(headers):
            raise ValidationError("CSV headers must be unique; rename duplicate columns and try again.", "file")
        rows = []
        for line, row in enumerate(reader, start=2 + skipped):
            values = {h: str(row.get(h, "") or "").strip() for h in headers}
            if _summary_row(list(values.values())):
                continue
            rows.append(values | {"__line__": str(line)})
        return headers, rows
    except csv.Error as exc:
        raise ValidationError(f"Could not read this CSV: {exc}", "file") from None
