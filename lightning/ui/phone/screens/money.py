"""Money (IV-3AY10, guideline C11.5): "What do I have, what do I owe, what is coming?". Net worth always today, the
balances themselves (four, then "See all") so any balance is one tap from any slot, Coming up (the next two bills,
never a late one: late bills are Home's To do and the Bills page), then what you owe, investments, goals and health as
one row each, each with its figure (IV-11H), and one row for reports and reviews. Under Net worth, its trend at each
month end and what you own as one bar by asset class (IV-11D4, C07.3.1 and A04). Services calculate; this module only
picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.planning import bill_state
from lightning.planning.bill_state import BillRow, BillState
from lightning.ui import charts
from lightning.ui.visuals import month_ends

ZERO = Decimal(0)
ACCOUNTS_SHOWN = 4
COMING_UP = 2   # IV-11H: twelve rows at most under the hero; the head opens every bill
BILLS_HORIZON_DAYS = 60   # BV-11L4: Coming up and Bills read the same window
UPCOMING = (BillState.DUE_SOON, BillState.BEFORE_PAYDAY, BillState.LATER)
TREND_MONTHS = 12
# A04.1: what you own in a fixed order, four then Other; a fund joins its family (the bar has no room for shades).
FAMILIES = (("cash", "Cash"), ("deposits", "Deposits"), ("gold", "Gold"), ("equity", "Stocks"), ("other", "Other"))
FAMILY_OF_TONE = {"cash": "cash", "deposits": "deposits", "money-market": "deposits", "fixed-income": "deposits",
                  "gold": "gold", "gold-fund": "gold", "equity": "equity", "equity-fund": "equity",
                  "other": "other", "other-fund": "other"}


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
    has_accounts: bool                # a fresh profile gets one first step instead of zero figures
    zakat: bool = False                # Zakat is on: its page is one of the places below
    goals_funded: int = 0              # goals and reserves at their target ("3 of 4 funded")
    goals_count: int = 0
    health_watch: int | None = None    # health figures outside their Good band; None when none has a limit
    working: object = None             # NF-12AB4: Net worth's working, for the hero's sheet
    trend: dict | None = None          # charts.trend of net worth at each month end; the last point is today
    own_split: tuple[dict, ...] = ()   # what you own by asset class family: {key, label, value, share}, A04 order
    strip: tuple[dict, ...] = ()       # NF-7AR3: today and the next 13 days of payments, each day a way into Upcoming


def _goals(c) -> tuple[int, int]:
    rows = [r for r in c.reserves.list_active() if r["target"] > ZERO]
    return sum(1 for r in rows if r["remaining"] <= ZERO), len(rows)


def _health_watch(c, day: date) -> int | None:
    bands = [f.band for f in c.health.figures(day) if f.band]
    return sum(1 for b in bands if b != "good") if bands else None


def net_worth_trend(c, day: date, count: int = TREND_MONTHS) -> dict:
    """Net worth at the end of each month, the last point today (C07.3.1): the hero's own figure ends the line."""
    points = [(key, c.position.at(end).net_worth) for key, end in month_ends(day, count, c.reporting.first_activity_date())]
    return charts.trend([k for k, _ in points], [{"name": "Net worth", "tone": "hold", "area": True,
                                                 "values": [v for _, v in points]}])


def own_split(position) -> tuple[dict, ...]:
    """What you own as one bar (A04): cash you own, then each holding class in its family, and the rest (a flat, a
    car) in Other. The parts add to What you own; a part at zero or below is left out of the bar and the rows."""
    totals = {key: ZERO for key, _ in FAMILIES}
    totals["cash"] += position.cash_you_own
    for cls in position.classes:
        totals[FAMILY_OF_TONE[charts.class_tone(cls.code)]] += cls.value
    totals["other"] += position.what_you_own - sum(totals.values(), ZERO)
    shown = [(key, label, totals[key]) for key, label in FAMILIES if totals[key] > ZERO]
    whole = sum((v for _, _, v in shown), ZERO)
    return tuple({"key": key, "label": label, "value": value, "share": float(value / whole * 100)}
                 for key, label, value in shown) if whole > ZERO else ()


def _balances(c, day: date) -> list[AccountRow]:
    rows = []
    for account in c.accounts.list(active_only=True):
        if account.parent_id:      # a currency pocket is part of its broker's row
            continue
        value = c.reporting.account_value(account.id, day)
        if value is not None:
            rows.append(AccountRow(account.id, account.name, value))
    rows.sort(key=lambda r: (-r.balance, r.name.casefold()))
    return rows


def _strip(c, day: date) -> tuple[dict, ...]:
    """Coming up's two weeks (NF-7AR3), the phone Upcoming tab's own strip; no forecast here, so no short mark."""
    if not c.planning.items():
        return ()
    from lightning.planning.calendar import payment_window
    from lightning.ui.phone.presenters.upcoming import STRIP_DAYS, strip_days
    return tuple(strip_days(payment_window(c.planning, c.gameya, day, STRIP_DAYS)))


def build(c, day: date) -> MoneyScreen:
    now = c.position.at(day)
    try:  # the Overview's own figure: the day before the month began to today (PositionService, one home)
        since, _reason = c.position.change_in_net_worth(day.replace(day=1), day)
    except Exception:  # history that cannot be rebuilt: the hero then says nothing about change
        since = None
    rows = _balances(c, day)
    bills = bill_state.unpaid_bills(c.planning, day, BILLS_HORIZON_DAYS)
    funded, goals = _goals(c)
    return MoneyScreen(
        working=now.net_worth_working, net_worth=now.net_worth, what_you_own=now.what_you_own, what_you_owe=now.what_you_owe, since_start=since,
        accounts=tuple(rows[:ACCOUNTS_SHOWN]), accounts_more=max(len(rows) - ACCOUNTS_SHOWN, 0),
        accounts_total=sum((r.balance for r in rows), ZERO), held_for_others=now.held_for_others,
        coming_up=tuple(b for b in bills if b.state in UPCOMING)[:COMING_UP],
        late_count=sum(1 for b in bills if b.state in (BillState.LATE, BillState.LATE_STALE)),
        holdings_value=now.holdings_value, has_accounts=bool(c.accounts.list()), zakat=c.zakat.enabled(),
        goals_funded=funded, goals_count=goals, health_watch=_health_watch(c, day),
        trend=net_worth_trend(c, day), own_split=own_split(now), strip=_strip(c, day))


@dataclass(frozen=True)
class AccountsPage:
    rows: tuple[AccountRow, ...]       # every balance, largest first
    total: Decimal
    held_for_others: Decimal


def accounts_page(c, day: date) -> AccountsPage:
    """Every balance (the page behind Money's "N more"): the list is the balances themselves, no fields."""
    rows = _balances(c, day)
    return AccountsPage(tuple(rows), sum((r.balance for r in rows), ZERO), c.position.at(day).held_for_others)


@dataclass(frozen=True)
class BillsPage:
    late: tuple[BillRow, ...]          # one question, not a wall of red rows
    week: tuple[BillRow, ...]
    before_payday: tuple[BillRow, ...]
    after_payday: tuple[BillRow, ...]


def bills_page(c, day: date) -> BillsPage:
    """The one bill state, grouped for the phone (C11.5): Late first as a block, then this week, before payday and after.
    The same open bills Home's To do and Money's Coming up read, so a bill is counted once everywhere."""
    rows = bill_state.unpaid_bills(c.planning, day, BILLS_HORIZON_DAYS)
    pick = lambda *states: tuple(b for b in rows if b.state in states)  # noqa: E731
    return BillsPage(pick(BillState.LATE, BillState.LATE_STALE), pick(BillState.DUE_SOON),
                     pick(BillState.BEFORE_PAYDAY), pick(BillState.LATER))
