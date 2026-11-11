"""Totals over account rows, as the Accounts pages list them (IT-12AE4: the screen reads these).

A row is (account, balance, what of it is yours, transaction count); a balance is None when it cannot be valued,
and a total with an unvalued part is None too, never a partial figure."""
from __future__ import annotations

from decimal import Decimal

from lightning.core.money import ZERO


def _add(a, b):
    return None if a is None or b is None else a + b


def roll_up_pockets(rows: list[tuple]) -> list[tuple]:
    """One row per broker (owner decision 2026-10-16): each currency pocket (an account with a parent) adds its
    balance, owned part and count to its parent's row, and leaves the list; a pocket whose parent is not listed stays."""
    rows = list(rows)
    by_id = {row[0].id: i for i, row in enumerate(rows)}
    for account, balance, owned, count in [row for row in rows if row[0].parent_id]:
        i = by_id.get(account.parent_id)
        if i is None:
            continue
        parent, p_balance, p_owned, p_count = rows[i]
        rows[i] = (parent, _add(p_balance, balance), _add(p_owned, owned), p_count + count)
    return [row for row in rows if not row[0].parent_id or row[0].parent_id not in by_id]


def active_total(rows: list[tuple]):
    """The balances of the active accounts added up (0 when there are none)."""
    return sum((row[1] for row in rows if row[0].active), start=0)


def group_totals(rows: list[tuple], group_of) -> dict[str, dict]:
    """Rows grouped by ``group_of(account)``, in first-seen order, each group with the balance and owned total
    of its active accounts."""
    groups: dict[str, dict] = {}
    for row in rows:
        group = groups.setdefault(group_of(row[0]), {"rows": [], "balance": ZERO, "owned": ZERO})
        group["rows"].append(row)
        if row[0].active:
            group["balance"] = _add(group["balance"], row[1])
            group["owned"] = _add(group["owned"], row[2])
    return groups


def held_for_others(total: Decimal, owned: Decimal) -> Decimal:
    """What an account holds for others: its value less the part that is yours."""
    return total - owned


def with_investments(cash: Decimal | None, invested: Decimal, unpriced: bool) -> Decimal | None:
    """A currency's cash and its investments together; None when either cannot be valued."""
    return None if unpriced or cash is None else cash + invested
