"""Checking a statement against its own Balance column (IT-7AA9). Pure: no database.

Each line's balance minus the line before it should equal the line's amount. A line where it does not means rows
between the two are missing, or one was counted twice: shown before the person leaves the review.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from lightning.core.dates import parse_date
from lightning.core.errors import ValidationError


@dataclass(frozen=True)
class BalanceGap:
    line: str
    previous_line: str
    moved: Decimal    # what the statement's balance did between the two lines
    added: Decimal    # what the line's own amount says


def _num(text) -> Decimal | None:
    try:
        from lightning.bank_import_rows import _decimal_amount
        return _decimal_amount(str(text))
    except (ValueError, ArithmeticError, InvalidOperation):
        return None


def balance_gaps(rows: list[dict], limit: int = 5) -> list[BalanceGap]:
    """Gaps in file order, oldest line first. Needs a Balance on both lines; a line without one breaks the chain."""
    usable = []
    for row in rows:
        balance = _num(row.get("Balance", "")) if (row.get("Balance") or "").strip() else None
        amount = _num(row.get("Amount", ""))
        try:
            day = parse_date(row.get("Date", ""))
        except ValidationError:
            day = None
        usable.append((row, balance, amount, day))
    days = [d for *_rest, d in usable if d]
    if len(days) > 1 and days[0] > days[-1]:
        usable.reverse()  # newest first: read it oldest first
    gaps, previous = [], None
    for row, balance, amount, _day in usable:
        if balance is None or amount is None or row.get("_errors"):
            previous = None
            continue
        if previous is not None and previous[0] + amount != balance:
            gaps.append(BalanceGap(str(row.get("_line", "")), previous[1], balance - previous[0], amount))
        previous = (balance, str(row.get("_line", "")))
    return gaps[:limit]
