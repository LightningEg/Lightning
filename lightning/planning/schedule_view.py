"""The schedule view: what the plan has scheduled, built once per request and handed to Budget's calls.

Budgeting sits below Planning, so it cannot import it. Planning builds this read-only view and the callers pass it
in (``schedule=``), instead of Budget reaching up through functions the composition root wired (IT-9K)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from lightning.core.dates import parse_month, today
from lightning.core.memo import request_cached
from lightning.core.money import ZERO


def reserve_goal_needs(reserves, month: str, as_of: date | None = None) -> list[dict]:
    """Informational monthly saving needs for dated project reserves."""
    day = as_of or today()
    month_start, _ = parse_month(month)
    result = []
    for reserve in reserves.list_active():
        if reserve["kind"] == "EMERGENCY" or reserve.get("planned_item_id") or not reserve.get("due_date"):
            continue
        due = date.fromisoformat(reserve["due_date"])
        if due < month_start:
            continue
        # Everything set aside so far counts, including what the goal has already paid for: a goal
        # funded in full and partly spent needs nothing more (audit 2026-10-05 #8).
        missing = max(reserve["target"] - reserve["allocated"], ZERO)
        months_left = max((due.year - day.year) * 12 + due.month - day.month + 1, 1)
        amount = (missing / months_left).quantize(Decimal("0.01"))
        if amount:
            result.append({"id": reserve["id"], "name": reserve["name"], "amount": amount,
                           "due_date": reserve["due_date"], "missing": missing})
    return result


class PlanSchedule:
    """Read-only: loan payments, bills, recurring income and reserve-goal needs, month by month (budgeting.ScheduleView)."""

    def __init__(self, planning, reserves):
        self._planning = planning
        self._reserves = reserves

    def loans(self, month: str) -> dict[int, Decimal]:
        return self._planning.loan_payments_by_category(month)

    def bills(self, month: str) -> dict[int, dict]:
        return self._planning.budget_fill_schedule(month)

    def income(self) -> Decimal | None:
        return self._planning.income_a_month()

    def goal_needs(self, month: str) -> list[dict]:
        return reserve_goal_needs(self._reserves, month)


class ScheduleSource:
    """Builds the schedule view; inside a request every caller gets the same one."""

    def __init__(self, planning, reserves):
        self._planning = planning
        self._reserves = reserves

    @request_cached
    def view(self) -> PlanSchedule:
        return PlanSchedule(self._planning, self._reserves)
