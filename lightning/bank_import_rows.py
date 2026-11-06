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
OPTIONAL = ("Counterparty", "Category", "Group", "Notes", "Reference", "Direction", "Currency", "Account")
SEPARATE_AMOUNT_FIELDS = ("Inflow", "Outflow")
MAX_BYTES = MAX_CSV_IMPORT_BYTES

INTERNAL_WORDS = {"internal", "internal transfer", "transfer", "transfers", "own account"}


# Rows another app wrote to set or correct its own balance. Lightning keeps the account's opening balance and its
# reconciliations itself, so posting these would count the money twice (owner feedback, 2026-11-05).
BALANCE_WORDS = {"starting balance", "starting balances", "opening balance", "opening balances", "initial balance",
                 "balance adjustment", "balance adjustments", "adjustment", "adjustments", "balance correction",
                 "reconciliation", "reconciliation adjustment"}


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
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("Save the statement as a UTF-8 CSV file.", "file") from None
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
        reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
        headers = [str(h or "").strip() for h in (reader.fieldnames or [])]
        if not headers or any(not h for h in headers):
            raise ValidationError("The CSV needs a header row with column names.", "file")
        if len(set(headers)) != len(headers):
            raise ValidationError("CSV headers must be unique; rename duplicate columns and try again.", "file")
        rows = []
        for line, row in enumerate(reader, start=2):
            rows.append({h: str(row.get(h, "") or "").strip() for h in headers} | {"__line__": str(line)})
        return headers, rows
    except csv.Error as exc:
        raise ValidationError(f"Could not read this CSV: {exc}", "file") from None
