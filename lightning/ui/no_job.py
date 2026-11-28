"""The "no job yet" nudge under Safe to spend (owner, 2026-11-27, r40 F8, r41 phase 1).

Safe to spend keeps its figure. When it is more than a month of usual spending, the money the plan has not given a
job is offered one: the emergency fund or a goal, investing, or this month's payday plan. Nothing moves until the
person chooses on that page. No new figure: the nudge names Safe to spend itself."""
from __future__ import annotations

from decimal import Decimal


def no_job_yet(safe_to_spend: Decimal, monthly_spending: Decimal | None, has_income: bool) -> dict | None:
    """The nudge when Safe to spend is larger than a month of usual spending, else None. With no usual spending yet
    (a new profile) or no income planned there is nothing to compare with, so it stays quiet."""
    if not has_income or not monthly_spending or monthly_spending <= 0 or safe_to_spend <= monthly_spending:
        return None
    return {"amount": safe_to_spend,
            "links": (("Emergency fund or a goal", "/plan/reserves"), ("Invest", "/investments/planner"),
                      ("This month's payday plan", "/payday"))}
