"""Money (IV-3AY10, guideline C11.5): "What do I have, what do I owe, what is coming?". Net worth always today, the
balances themselves (four, then "N more") so any balance is one tap from any slot, Coming up (the next three bills,
never a late one: late bills are Home's To do and the Bills page), then what you owe, investments, goals and health as
one row each. Services calculate; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.core.dates import month_of
from lightning.planning import bill_state
from lightning.planning.bill_state import BillRow, BillState

ZERO = Decimal(0)
ACCOUNTS_SHOWN = 4
COMING_UP = 3
UPCOMING = (BillState.DUE_SOON, BillState.BEFORE_PAYDAY, BillState.LATER)


@dataclass(frozen=True)
class AccountRow:
    id: int
    name: str
    balance: Decimal


@dataclass(frozen=True)
class MoneyScreen:
    net_worth: Decimal
    what_you_own: Decimal
    what_you_owe: Decimal
    since_start: Decimal | None        # net worth now less at the start of the month; None when it cannot be known
    accounts: tuple[AccountRow, ...]   # the first ACCOUNTS_SHOWN, largest first
    accounts_more: int
    accounts_total: Decimal
    held_for_others: Decimal           # the one quiet line when accounts differ from what you own
    coming_up: tuple[BillRow, ...]     # at most COMING_UP, never late
    late_count: int                    # late bills are one pointer to Home's catch-up, not rows here
    holdings_value: Decimal


def _balances(c, day: date) -> list[AccountRow]:
    rows = []
    for account in c.accounts.list(active_only=True):
        if account.parent_id or account.account_type.value in ("PHYSICAL_ASSET", "OTHER_ASSET"):
            continue
        value = c.reporting.account_value(account.id, day)
        if value is not None:
            rows.append(AccountRow(account.id, account.name, value))
    rows.sort(key=lambda r: (-r.balance, r.name.casefold()))
    return rows


def build(c, day: date) -> MoneyScreen:
    now = c.position.at(day)
    try:
        start = c.position.at(day.replace(day=1)).net_worth
        since = now.net_worth - start
    except Exception:  # history that cannot be rebuilt: the hero then says nothing about change
        since = None
    rows = _balances(c, day)
    bills = bill_state.open_bills(c.planning, day, bill_state.SOON_DAYS * 3)
    return MoneyScreen(
        net_worth=now.net_worth, what_you_own=now.what_you_own, what_you_owe=now.what_you_owe, since_start=since,
        accounts=tuple(rows[:ACCOUNTS_SHOWN]), accounts_more=max(len(rows) - ACCOUNTS_SHOWN, 0),
        accounts_total=sum((r.balance for r in rows), ZERO), held_for_others=now.held_for_others,
        coming_up=tuple(b for b in bills if b.state in UPCOMING)[:COMING_UP],
        late_count=sum(1 for b in bills if b.state in (BillState.LATE, BillState.LATE_STALE)),
        holdings_value=now.holdings_value)
