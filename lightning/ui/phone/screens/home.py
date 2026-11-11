"""Home (IV-3AY6, IV-11E, guideline C11.1): "Am I OK today, and what do I do next?". Always today: the Safe to spend
hero with its working and about how much a day, To do (three rows: name, figure, when, one verb), Latest five, This month. The state (first run, catch-up, payday,
overspent, calm; C13) decides what leads. Services calculate; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import month_of, parse_date
from lightning.ui.phone.screens.budget import month_bar
from lightning.planning import bill_state
from lightning.planning.domain import PlanKind
from lightning.transactions.domain import DocType
from lightning.workflows.review import ReviewInbox
from lightning.workflows.todo import TodoRow, todo_rows

TODO_SHOWN = 3


def _shown(rows) -> tuple:
    """To do's three rows. After days away the Catch up row is always one of them (guideline C13): bills that fill the
    list would hide the one question that clears the long-overdue ones, so it takes the last place instead."""
    first = list(rows[:TODO_SHOWN])
    away = next((r for r in rows[TODO_SHOWN:] if r.kind == "catch_up"), None)
    if away is not None:
        first[-1] = away
    return tuple(first)
LATEST = 5
STATES = ("first_run", "catch_up", "payday", "overspent", "calm")


@dataclass(frozen=True)
class PaydayMeter:
    """C06.1 meter with a tick under Safe to spend (IV-11D1): the fill is everyday money gone, the tick is where the
    pace is today; ahead (rose) when spending is past the pace, Budget's own verdict (EverydayBudget.pace_gap)."""
    spent: float    # percent of the everyday plan spent, 0 to 100
    pace: float     # percent the pace allows by today, 0 to 100
    ahead: bool


def payday_meter(everyday) -> PaydayMeter | None:
    """The meter from the same EverydayBudget the hero's line reads, so the line, the meter and Budget agree."""
    if everyday is None or not everyday.current:
        return None
    spent, pace = everyday.spent_share, everyday.pace_share
    if spent is None or pace is None:
        return None
    return PaydayMeter(round(float(spent * 100), 1), round(float(pace * 100), 1), everyday.pace_gap > 0)


@dataclass(frozen=True)
class HomeScreen:
    state: str
    safe: Decimal | None               # None until the first run is done
    until: str                         # the next income date, "" when none is planned
    per_day: Decimal | None            # Budget's everyday figure a day (EverydayBudget.per_day); None with no plan
    per_day_days: int                  # the days it is spread over, today included
    per_day_to_payday: bool            # those days run to payday: no payday before the month ends (owner, 2026-11-09)
    meter: PaydayMeter | None          # IV-11D1: under the hero; None with no plan or no everyday money planned
    working: object                            # Safe to spend's working (lightning.core.working), for its sheet
    todo: tuple[TodoRow, ...]          # at most TODO_SHOWN
    todo_total: int
    latest: tuple                      # register rows, at most LATEST
    spent: Decimal
    left_in_plan: Decimal | None       # None when the month has no plan
    month: str
    catch_up: bill_state.CatchUp
    month_bar: dict | None = None      # IV-11D2: the plan as one bar (spent, left, over); None without a plan


def _first_run(c) -> bool:
    return not c.accounts.list() or not c.planning.items((PlanKind.INCOME,))


def build(c, day: date) -> HomeScreen:
    inbox = ReviewInbox(c)
    items = inbox.items(day)
    forecast = inbox.forecast
    bills = bill_state.open_bills(c.planning, day, bill_state.SOON_DAYS)
    away = bill_state.catch_up(c, day, bills)
    last_income = bill_state.last_income_date(c.planning, day)
    paid_today = bool(last_income and (day - parse_date(last_income)).days <= 1)  # income arrived today or yesterday
    rows = todo_rows(c, day, bills, items, away, paid_today)
    safe = forecast.safe_to_spend
    until = forecast.next_income_date or ""
    month = month_of(day)
    schedule = c.schedules.view()
    plan = c.budgets.plan_summary(month, schedule=schedule) if c.budgets.has_plan(month, schedule=schedule) else None
    # The hero's line is Budget's own everyday figure a day (owner, 2026-11-09: one daily allowance, BV-12A), never
    # Safe to spend divided by the days: two figures a day would answer one question twice.
    everyday = c.forecaster.everyday(month, day) if plan else None
    per_day = everyday.per_day if everyday else None
    next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    recent, total, _ = c.reporting.register_page(None, "1900-01-01", "9999-12-31", 1, 30)
    latest = tuple([r for r in recent if r.type != DocType.VAL][:LATEST])
    if _first_run(c):
        state = "first_run"
    elif away.away:
        state = "catch_up"
    elif any(r.kind == "payday" for r in rows):
        state = "payday"
    elif safe < 0:
        state = "overspent"
    else:
        state = "calm"
    first_run = state == "first_run"
    return HomeScreen(state=state, safe=None if first_run else safe, until=until, per_day=per_day,
                      per_day_days=everyday.days_left if everyday else 0,
                      per_day_to_payday=bool(until) and until <= next_month.isoformat(),
                      meter=None if first_run else payday_meter(everyday),
                      working=forecast.safe_to_spend_working,
                      todo=_shown(rows), todo_total=len(rows), latest=latest,
                      spent=c.reporting.cash_flow(day.replace(day=1), day).outflows,
                      left_in_plan=plan["left"] if plan else None, month=month, catch_up=away,
                      month_bar=month_bar(plan["planned"], plan["spent"]) if plan else None)
