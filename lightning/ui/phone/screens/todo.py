"""To do's "See all" (IV-3AY14): every row Home's To do would show, not cut to three, in the same order. The rows come
from the same services and the same ``todo_rows`` call as Home, so the two never disagree."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from lightning.core.dates import parse_date
from lightning.planning import bill_state
from lightning.workflows.review import ReviewInbox
from lightning.workflows.todo import TodoRow, todo_rows


@dataclass(frozen=True)
class TodoScreen:
    rows: tuple[TodoRow, ...]


def build(c, day: date) -> TodoScreen:
    items = ReviewInbox(c).items(day)
    bills = bill_state.open_bills(c.planning, day, bill_state.SOON_DAYS)
    away = bill_state.catch_up(c, day, bills)
    last_income = bill_state.last_income_date(c.planning, day)
    paid_today = bool(last_income and (day - parse_date(last_income)).days <= 1)  # not money
    return TodoScreen(rows=tuple(todo_rows(c, day, bills, items, away, paid_today)))
