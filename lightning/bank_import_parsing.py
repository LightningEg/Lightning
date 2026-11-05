"""Normalize reviewed CSV rows using the shared upstream row readers."""
from decimal import Decimal

from lightning.bank_import_names import clean_name

from lightning.bank_import_rows import (
    REQUIRED, OPTIONAL, SEPARATE_AMOUNT_FIELDS, DIRECTION_FIELD,
    _date, _direction, _separate_amount, _amount,
)


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
            if amount_model == "SINGLE" and mapping.get(DIRECTION_FIELD):
                # A positive amount beside DR is money out: the marker decides the sign, not the digits.
                sign = _direction(raw.get(mapping[DIRECTION_FIELD], ""))
                parsed["Amount"] = format(abs(Decimal(parsed["Amount"])) * sign, "f")
            if invert_amount:
                parsed["Amount"] = format(-Decimal(parsed["Amount"]), "f")
        except ValueError as exc:
            errors.append(str(exc))
        # The payee is inside the bank's wording (7AC): "POS PURCHASE CARREFOUR MAADI" is Carrefour. With only a
        # description column it names the payee too; the bank's own text stays in Notes.
        written = " ".join(str(parsed.get("Counterparty") or "").split())
        description = " ".join(str(parsed.get("Notes") or "").split())
        if written:
            cleaned = clean_name(written)
            if cleaned != written:
                parsed["Counterparty"] = cleaned
                parsed["Notes"] = description or written
        elif description and not mapping.get("Counterparty"):  # no payee column at all, not a payee left empty
            parsed["Counterparty"] = clean_name(description)
        parsed["_line"] = raw["__line__"]
        parsed["_errors"] = errors
        stored.append((raw, parsed))
    return stored
