"""CSV decoding and value normalization for reviewed bank imports."""
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
MAX_BYTES = MAX_CSV_IMPORT_BYTES


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



def normalize_rows(raw_rows, mapping, amount_model, invert_amount):
    """Build the same review rows and row-level errors without changing the ledger."""
    fields = ("Date", *SEPARATE_AMOUNT_FIELDS, *OPTIONAL) if amount_model == "SEPARATE" else (*REQUIRED, *OPTIONAL)
    stored = []
    for raw in raw_rows:
        parsed = {key: raw.get(mapping.get(key, ""), "") for key in fields}
        for key in ("Amount", *SEPARATE_AMOUNT_FIELDS):
            parsed.setdefault(key, "")
        errors = []
        try:
            parsed["Date"] = _date(parsed["Date"])
            parsed["Amount"] = (_separate_amount(parsed["Inflow"], parsed["Outflow"])
                                if amount_model == "SEPARATE" else _amount(parsed["Amount"]))
            if invert_amount:
                parsed["Amount"] = format(-Decimal(parsed["Amount"]), "f")
        except ValueError as exc:
            errors.append(str(exc))
        parsed["_line"] = raw["__line__"]
        parsed["_errors"] = errors
        stored.append((raw, parsed))
    return stored
