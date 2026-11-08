"""Normalize reviewed CSV rows using the shared upstream row readers."""
from decimal import Decimal

from lightning.core.errors import ValidationError
from lightning.import_profile import profile_dates, read_date
from lightning.bank_import_rows import (
    REQUIRED, OPTIONAL, SEPARATE_AMOUNT_FIELDS,
    _date, _separate_amount, _amount, direction_sign, currency_code, clean_merchant, SkipRow, is_total_line,
)


def normalize_rows(raw_rows, mapping, amount_model, invert_amount, account_currency=None, account_check=None, date_profile=None):
    """Build the same review rows and row-level errors without changing the ledger."""
    fields = (("Date", *SEPARATE_AMOUNT_FIELDS, *OPTIONAL) if amount_model == "SEPARATE"
              else ("Date", *OPTIONAL) if amount_model == "BALANCE" else (*REQUIRED, *OPTIONAL))
    raw_rows = list(raw_rows)
    date_profile = date_profile or profile_dates(raw.get(mapping.get("Date", ""), "") for raw in raw_rows)
    stored = []
    if amount_model == "BALANCE":
        raw_rows = list(raw_rows)
        balance_moves = _balance_moves(raw_rows, mapping, date_profile)
    for position, raw in enumerate(raw_rows):
        parsed = {key: raw.get(mapping.get(key, ""), "") for key in fields}
        for key in ("Amount", *SEPARATE_AMOUNT_FIELDS):
            parsed.setdefault(key, "")
        if amount_model == "BALANCE":
            parsed["Amount"] = balance_moves[position]
        errors = []
        if not parsed["Date"].strip() and is_total_line(*(raw.get(h, "") for h in raw if h != "__line__")):
            parsed["_skip_reason"] = "A totals or balance line, not a transaction: skipped."
            parsed["Amount"] = "0"
            parsed["_line"], parsed["_errors"] = raw["__line__"], errors
            stored.append((raw, parsed))
            continue
        try:
            try:
                parsed["Date"] = read_date(parsed["Date"], date_profile).isoformat()
            except ValidationError as exc:
                raise ValueError(exc.message) from None
            parsed["Date"] = _date(parsed["Date"])
            parsed["Amount"] = (_separate_amount(parsed["Inflow"], parsed["Outflow"])
                                if amount_model == "SEPARATE" else _amount(parsed["Amount"]))
            if amount_model == "BALANCE" and position == balance_moves.first:
                raise SkipRow("The statement's first balance, not a payment: Lightning keeps the account's "
                              "opening balance itself.")
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
        if not mapping.get("Counterparty") and (parsed.get("Notes") or "").strip() and not parsed.get("Counterparty"):
            # A bank statement names the merchant only inside its description: the cleaned name is the counterparty,
            # and the bank's own wording stays in Notes (IT-7AA4).
            parsed["Counterparty"] = clean_merchant(parsed["Notes"])
        sub = (parsed.get("Subcategory") or "").strip()
        if sub and (parsed.get("Category") or "").strip() and not (parsed.get("Group") or "").strip():
            # Another app's Category and Subcategory columns: the first is the group, the second the name.
            parsed["Group"], parsed["Category"] = parsed["Category"].strip(), sub
        elif sub and not (parsed.get("Category") or "").strip():
            parsed["Category"] = sub
        parsed["_line"] = raw["__line__"]
        parsed["_errors"] = errors
        stored.append((raw, parsed))
    _join_split_lines(stored)
    return stored


def _readable(text: str) -> bool:
    try:
        Decimal(text)
        return True
    except ArithmeticError:
        return False


class _Moves(list):
    first = -1  # the row whose balance has nothing before it: the statement's earliest line


def _balance_moves(raw_rows, mapping, date_profile) -> _Moves:
    """IT-7AA5: a statement with only a Balance column. Each row's amount is the change from the balance before it
    (the earlier line, whichever way the file is sorted); the earliest line has none, so it opens as a skip."""
    from lightning.bank_import_rows import _decimal_amount
    from lightning.import_profile import read_date
    balances, days = [], []
    for raw in raw_rows:
        try:
            balances.append(_decimal_amount(raw.get(mapping.get("Balance", ""), "")))
        except (ValueError, ArithmeticError):
            balances.append(None)
        try:
            days.append(read_date(raw.get(mapping.get("Date", ""), ""), date_profile))
        except ValueError:
            days.append(None)
    newest_first = bool(days and days[0] and days[-1] and days[0] > days[-1])
    order = list(range(len(raw_rows)))[::-1] if newest_first else list(range(len(raw_rows)))
    moves = _Moves(["0"] * len(raw_rows))
    moves.first = order[0] if order else -1
    previous = None
    for index in order:
        current = balances[index]
        if previous is not None and current is not None:
            moves[index] = format(current - previous, "f")
        if current is not None:
            previous = current
    return moves


def _join_split_lines(stored) -> None:
    """IT-7AA7: lines of one purchase (same day, total and name) each carrying a Split amount that together make
    the total become one row with its parts (`_file_split`); the other lines open as skips, never as duplicates."""
    groups: dict[tuple, list] = {}
    for _raw, parsed in stored:
        if parsed.get("Split") and not parsed["_errors"] and not parsed.get("_skip_reason"):
            groups.setdefault((parsed["Date"], parsed["Amount"], (parsed.get("Counterparty") or "").casefold()), []).append(parsed)
    for lines in groups.values():
        if len(lines) < 2:
            continue
        try:
            parts = [abs(Decimal(str(_amount(line["Split"])))) for line in lines]
        except (ValueError, ArithmeticError):
            continue
        if sum(parts) != abs(Decimal(lines[0]["Amount"])):
            continue
        lines[0]["_file_split"] = [{"group": (line.get("Group") or "").strip(), "category": (line.get("Category") or "").strip(),
                                    "amount": format(part, "f")} for line, part in zip(lines, parts)]
        for line in lines[1:]:
            line["_skip_reason"] = f"A part of the split on line {lines[0]['_line']}: posted once, there."
