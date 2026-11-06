"""Normalize reviewed CSV rows using the shared upstream row readers."""
from decimal import Decimal

from lightning.import_profile import profile_dates
from lightning.bank_import_rows import (
    REQUIRED, OPTIONAL, SEPARATE_AMOUNT_FIELDS,
    _date, _separate_amount, _amount, direction_sign, currency_code, SkipRow, is_total_line,
)


def normalize_rows(raw_rows, mapping, amount_model, invert_amount, account_currency=None, account_check=None):
    """Build the same review rows and row-level errors without changing the ledger."""
    fields = ("Date", *SEPARATE_AMOUNT_FIELDS, *OPTIONAL) if amount_model == "SEPARATE" else (*REQUIRED, *OPTIONAL)
    date_profile = profile_dates(raw.get(mapping.get("Date", ""), "") for raw in raw_rows)
    stored = []
    for raw in raw_rows:
        parsed = {key: raw.get(mapping.get(key, ""), "") for key in fields}
        for key in ("Amount", *SEPARATE_AMOUNT_FIELDS):
            parsed.setdefault(key, "")
        errors = []
        if not parsed["Date"].strip() and is_total_line(*(raw.get(h, "") for h in raw if h != "__line__")):
            parsed["_skip_reason"] = "A totals or balance line, not a transaction: skipped."
            parsed["Amount"] = "0"
            parsed["_line"], parsed["_errors"] = raw["__line__"], errors
            stored.append((raw, parsed))
            continue
        try:
            parsed["Date"] = _date(parsed["Date"], date_profile)
            parsed["Amount"] = (_separate_amount(parsed["Inflow"], parsed["Outflow"])
                                if amount_model == "SEPARATE" else _amount(parsed["Amount"]))
            if amount_model != "SEPARATE" and mapping.get("Direction"):
                parsed["Amount"] = format(abs(Decimal(parsed["Amount"])) * direction_sign(parsed["Direction"]), "f")
            if invert_amount:
                parsed["Amount"] = format(-Decimal(parsed["Amount"]), "f")
            code = currency_code(parsed.get("Currency", ""))
            if code and account_currency and code != account_currency:
                # IT-7AA3: another currency's figure is never the account's own. The person types the amount in the
                # account's currency in the review, or skips the row.
                raise ValueError(f"This row is in {code} but the account is in {account_currency}. "
                                 f"Change its amount to {account_currency} in the file, or skip the row.")
            message = account_check(parsed.get("Account", "")) if account_check else None
            if message:
                raise ValueError(message)
        except SkipRow as exc:
            parsed["_skip_reason"] = str(exc)
            if not parsed["Amount"].strip() or not _readable(parsed["Amount"]):
                parsed["Amount"] = "0"
        except ValueError as exc:
            errors.append(str(exc))
        parsed["_line"] = raw["__line__"]
        parsed["_errors"] = errors
        stored.append((raw, parsed))
    return stored


def _readable(text: str) -> bool:
    try:
        Decimal(text)
        return True
    except ArithmeticError:
        return False
