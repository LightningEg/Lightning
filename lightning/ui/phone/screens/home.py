"""Home (IV-3AY6, guideline C11.1): "Am I OK today, and what do I do next?". Always today: the Safe to spend hero with
its working, To do (three rows, one action each), Latest five, This month. The state (first run, catch-up, payday,
overspent, calm; C13) decides what leads. Services calculate; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.core.dates import month_of, parse_date
from lightning.planning import bill_state
from lightning.planning.domain import PlanKind
from lightning.transactions.domain import DocType
from lightning.workflows.review import ReviewInbox
from lightning.workflows.todo import TodoRow, todo_rows

TODO_SHOWN = 3
LATEST = 5
STATES = ("first_run", "catch_up", "payday", "overspent", "calm")


@dataclass(frozen=True)
class HomeScreen:
    state: str
    safe: Decimal | None               # None until the first run is done
    until: str                         # the next income date, "" when none is planned
    working: tuple[tuple[str, Decimal], ...]   # the parts of Safe to spend, for its sheet
    todo: tuple[TodoRow, ...]          # at most TODO_SHOWN
    todo_total: int
    latest: tuple                      # register rows, at most LATEST
    spent: Decimal
    left_in_plan: Decimal | None       # None when the month has no plan
    month: str
    catch_up: bill_state.CatchUp


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
    return HomeScreen(state=state, safe=None if first_run else safe, until=until,
                      working=tuple((name, value) for name, value in forecast.safe_to_spend_parts),
                      todo=tuple(rows[:TODO_SHOWN]), todo_total=len(rows), latest=latest,
                      spent=c.reporting.cash_flow(day.replace(day=1), day).outflows,
                      left_in_plan=plan["left"] if plan else None, month=month, catch_up=away)
