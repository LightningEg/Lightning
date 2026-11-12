"""Figures read straight off register rows and transaction lines (IT-12AE4): a transaction's cash amount, each day's
net on a phone list, and a day's value updates folded into one row. Screens read these; they work none of them out."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from lightning.core.money import ZERO


def cash_amount(lines) -> Decimal:
    """How much a transaction moved: what its cash lines add up to, unsigned."""
    return abs(sum((line.quantity for line in lines), start=0))


def day_nets(rows, show_account: bool = False) -> dict[str, Decimal]:
    """Each day's net on a phone list (phone overhaul 2026-10-22): money in less money out, in the base currency.
    Transfers, investment rows and value updates move nothing in or out, so they are left out. A day's net is shown only
    for a day with two or more rows (3AN12): one row already says it. show_account: the all-accounts list shows a
    transfer once, so its second leg is not a row."""
    nets: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for r in rows:
        if show_account and getattr(r, "type", "") == "TRF" and r.amount > 0:
            continue
        counts[r.date] = counts.get(r.date, 0) + 1
        if getattr(r, "type", "") in ("IN", "OUT"):
            nets[r.date] = nets.get(r.date, ZERO) + (r.amount_base or r.amount)
    return {day: net for day, net in nets.items() if counts.get(day, 0) >= 2}


def group_value_updates(rows) -> list:
    """A day's value updates (revaluations) become one "Investments moved" row on a phone list, so a month-end
    re-pricing never crowds out the money that moved. Other rows pass through unchanged."""
    out: list = []
    for r in rows:
        if r.type != "VAL":
            out.append(r)
            continue
        last = out[-1] if out else None
        if last is not None and last.type == "VALS" and last.date == r.date:
            last.count += 1
            last.amount += r.amount_base or r.amount
        else:
            out.append(SimpleNamespace(type="VALS", date=r.date, txn_id=r.txn_id, count=1, amount=r.amount_base or r.amount,
                                       balance=None))
    return out
