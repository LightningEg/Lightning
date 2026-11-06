"""Normalize reviewed CSV rows using the shared upstream row readers."""
from decimal import Decimal

from lightning.import_profile import profile_dates
from lightning.bank_import_rows import (
    REQUIRED, OPTIONAL, SEPARATE_AMOUNT_FIELDS,
    _date, _separate_amount, _amount,
)


def normalize_rows(raw_rows, mapping, amount_model, invert_amount):
    """Build the same review rows and row-level errors without changing the ledger."""
    fields = ("Date", *SEPARATE_AMOUNT_FIELDS, *OPTIONAL) if amount_model == "SEPARATE" else (*REQUIRED, *OPTIONAL)
    date_profile = profile_dates(raw.get(mapping.get("Date", ""), "") for raw in raw_rows)
    stored = []
    for raw in raw_rows:
        parsed = {key: raw.get(mapping.get(key, ""), "") for key in fields}
        for key in ("Amount", *SEPARATE_AMOUNT_FIELDS):
            parsed.setdefault(key, "")
        errors = []
        try:
            parsed["Date"] = _date(parsed["Date"], date_profile)
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
