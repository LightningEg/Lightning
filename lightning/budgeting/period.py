"""Budget figures over a period (a month, the year so far, all time or custom dates), as the Budget page shows them.

Moved out of the Budget route (IT-12AE4): Planned, Spent, Left, the carryover and the income basis of a period,
for the period, for each L1 group and for each category, with the same Decimal arithmetic the page always used.
A saved monthly limit stays whole in month, YTD and all-time views; only custom dates prorate it by days."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from lightning.categories.domain import Movement
from lightning.core.dates import parse_month
from lightning.core.money import ZERO, quantize


def month_factor(key: str, month: str, start: date, end: date) -> Decimal:
    """The share of a month's plan that falls inside the period: 1, or the days that overlap for custom dates."""
    m_first, m_last = parse_month(month)
    overlap_start, overlap_end = max(m_first, start), min(m_last, end)
    if key != "custom":
        return Decimal(1)
    if overlap_end < overlap_start:
        return ZERO
    return Decimal((overlap_end - overlap_start).days + 1) / Decimal((m_last - m_first).days + 1)


@dataclass
class BudgetPeriod:
    view: object
    month_views: list = field(default_factory=list)
    tracked: set = field(default_factory=set)
    by_group: dict = field(default_factory=dict)
    period_base: Decimal = ZERO
    period_opening: Decimal = ZERO
    period_carryover: Decimal = ZERO
    period_budgeted: Decimal = ZERO
    group_totals: dict = field(default_factory=dict)
    category_periods: dict = field(default_factory=dict)
    spending_start: date | None = None
    period_spending: dict = field(default_factory=dict)
    gross_spending: dict = field(default_factory=dict)
    period_income: Decimal = ZERO
    background_counts: dict = field(default_factory=dict)
    background_totals: dict = field(default_factory=dict)

    @property
    def period_actual(self) -> Decimal:
        return sum(self.period_spending.values(), ZERO)

    @property
    def gross_period_spending(self) -> Decimal:
        return sum(self.gross_spending.values(), ZERO)

    @property
    def funding_adjustment_total(self) -> Decimal:
        return self.gross_period_spending - self.period_actual

    @property
    def period_left(self) -> Decimal:
        return self.period_budgeted - self.period_actual

    @property
    def unplanned_spending(self) -> Decimal:
        return self.period_actual - sum((row["spent"] for row in self.group_totals.values()), ZERO)

    @property
    def plan_outside_groups(self) -> Decimal:
        return self.period_budgeted - sum((row["budgeted"] for row in self.group_totals.values()), ZERO)


def budget_period(budgets, categories, schedule, *, key: str, start: date, end: date, month: str) -> BudgetPeriod:
    """Every money figure of the Budget page for one period (``key`` is the period's kind)."""
    view = budgets.month_view(month, schedule=schedule)
    result = BudgetPeriod(view=view)
    cursor = start.replace(day=1)
    month_views = result.month_views
    while cursor <= end:
        month_key = cursor.strftime("%Y-%m")
        # A longer period includes only months with a saved plan, matching its spending window.
        if key == "month" or budgets.has_plan(month_key, schedule=schedule):
            month_views.append((month_key, budgets.month_view(month_key, schedule=schedule)))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    period_base = ZERO
    period_opening = ZERO
    period_carryover = ZERO
    if month_views:
        period_opening = month_views[0][1].available - month_views[0][1].budget
        period_carryover = period_opening
        if key == "custom":
            first_month = parse_month(month_views[0][0])
            overlap_start, overlap_end = max(first_month[0], start), min(first_month[1], end)
            opening_factor = (Decimal((overlap_end - overlap_start).days + 1)
                              / Decimal((first_month[1] - first_month[0]).days + 1))
            period_opening *= opening_factor
            period_carryover *= opening_factor
    group_totals = result.group_totals
    for _, month_view in month_views:
        factor = month_factor(key, month_view.month, start, end)
        period_base += month_view.budget * factor
        for section in month_view.sections:
            for group in section.groups:
                row = group_totals.setdefault(group.category_id, {"name": group.name, "section": section.name,
                    "budgeted": ZERO, "carryover": ZERO, "spent": ZERO, "left": ZERO})
                row["budgeted"] += (group.budget or ZERO) * factor
                if month_views and month_view.month == month_views[0][0]:
                    row["budgeted"] += group.opening_carryover * factor
                    row["carryover"] += group.opening_carryover * factor
    for row in group_totals.values():
        row["left"] = row["budgeted"] - row["spent"]
    if key == "month":
        for section in view.sections:
            for group in section.groups:
                row = group_totals.get(group.category_id)
                if row:
                    row["budgeted"] = group.available or ZERO
                    row["carryover"] = group.opening_carryover
                    row["left"] = quantize(row["budgeted"], 0) - quantize(row["spent"], 0)
    children: dict[int, list[int]] = {}
    for category in categories.tree(Movement.OUTFLOW):
        if category.parent_id:
            children.setdefault(category.parent_id, []).append(category.id)

    def category_tree_ids(category_id):
        descendants = {category_id}
        pending = [category_id]
        while pending:
            kids = children.get(pending.pop(), [])
            descendants.update(kids)
            pending.extend(kids)
        return descendants

    for section in view.sections:
        for group in section.groups:
            result.by_group[group.category_id] = sorted(category_tree_ids(group.category_id) - {group.category_id})
    for line in budgets.background(month, schedule=schedule):
        result.background_counts[line["group_id"]] = result.background_counts.get(line["group_id"], 0) + 1
        result.background_totals[line["group_id"]] = (result.background_totals.get(line["group_id"], ZERO)
                                                      + (line["estimate"] or ZERO))
    result.tracked = tracked = budgets.tracked_ids(month, schedule=schedule)
    # Background estimates are monthly expectations for untracked leaf
    # categories. Parent direct plans already cap these expenses, so children
    # under those caps are not added a second time.
    for _, month_view in month_views:
        factor = month_factor(key, month_view.month, start, end)
        for line in budgets.background(month_view.month, tracked=tracked, schedule=schedule):
            if line["estimate"] is not None and line["group_id"] in group_totals:
                group_totals[line["group_id"]]["budgeted"] += line["estimate"] * factor
                period_base += line["estimate"] * factor
    one_offs = budgets.one_off_ids()
    # Planned and Spent cover the same months: a long period (YTD, All time, custom) counts spending
    # from the first month that has a plan, because months before it have nothing planned.
    plan_months = [k for k, _ in month_views if budgets.has_plan(k, schedule=schedule)]
    spending_start = start
    if key != "month" and plan_months:
        spending_start = max(start, parse_month(plan_months[0])[0])
    result.spending_start = spending_start
    gross_spending = {cid: value for cid, value in budgets.owned_spending(spending_start, end).items()
                      if cid not in one_offs}
    period_spending = {cid: v for cid, v in budgets.plan_funded_spending(spending_start, end).items()
                       if cid not in one_offs}  # one-off spending stays in cash flow, out of the budget
    result.gross_spending, result.period_spending = gross_spending, period_spending
    category_periods = result.category_periods
    for _, month_view in month_views:
        factor = month_factor(key, month_view.month, start, end)
        for section in month_view.sections:
            for line in section.lines:
                if line.depth <= 1:
                    continue
                row = category_periods.setdefault(line.category_id, {
                    "base_budget": ZERO, "carryover": ZERO, "current_budget": ZERO,
                    "budgeted": ZERO, "spent": ZERO,
                })
                row["base_budget"] += (line.budget or ZERO) * factor
                if month_views and month_view.month == month_views[0][0]:
                    row["carryover"] += line.opening_carryover * factor
    for category_id, row in category_periods.items():
        row["current_budget"] = row["base_budget"] + row["carryover"]
        row["budgeted"] = row["current_budget"]
        row["spent"] = sum((period_spending.get(cid, ZERO) for cid in category_tree_ids(category_id)), ZERO)
        row["gross"] = sum((gross_spending.get(cid, ZERO) for cid in category_tree_ids(category_id)), ZERO)
        row["funding_adjustment"] = row["gross"] - row["spent"]
        row["left"] = quantize(row["current_budget"], 0) - quantize(row["spent"], 0)  # as the figures beside it read
    for group_id, child_ids in result.by_group.items():
        row = group_totals.get(group_id)
        if row:
            row["spent"] = sum((period_spending.get(cid, ZERO) for cid in child_ids), ZERO)
            row["left"] = quantize(row["budgeted"], 0) - quantize(row["spent"], 0)
    period_income = ZERO
    for month_key, _ in month_views:
        basis = budgets.budgeting_income(month_key, schedule=schedule) or ZERO
        period_income += basis * month_factor(key, month_key, start, end)
    result.period_income = period_income
    result.period_base, result.period_opening, result.period_carryover = period_base, period_opening, period_carryover
    result.period_budgeted = period_base + period_opening
    return result


SMALL_OVER = Decimal(100)  # BU-2: below this, or under 5% of its plan, an overspend is a rose bar, not a Needs you row


def over_matters(over_by: Decimal, planned: Decimal | None) -> bool:
    """An overspend raises Needs you when it matters: 100 or more and 5% or more of the category's plan (BU-2)."""
    return over_by >= SMALL_OVER and over_by >= (planned or ZERO) * Decimal("0.05")


def spent_percent(spent: Decimal, planned: Decimal) -> int:
    """Spent as a whole percent of the plan, never below zero (the phone's plan ring)."""
    return max(int((spent / planned * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)), 0)


def plan_used(planned: Decimal, left: Decimal) -> tuple[Decimal, Decimal | None]:
    """What of a month's plan is used, and that as a percent of the plan (None with nothing planned)."""
    used = planned - left
    return used, (used / planned * 100 if planned > 0 else None)


def category_pace(planned: Decimal, spent: Decimal, first: date, last: date, day: date) -> dict:
    """One category's month against its plan: Left (whole, as the figures beside it read), the share spent, the
    share of the month gone (None outside the month) and whether spending runs 10 points ahead of it."""
    left = quantize(planned, 0) - quantize(spent, 0)
    share = spent / planned * 100
    current = first <= day <= last
    days = (last - first).days + 1
    pace = (Decimal((day - first).days + 1) / days * 100) if current else None
    return {"left": left, "share": share, "current": current, "pace": pace,
            "risk": left >= ZERO and pace is not None and share >= pace + 10}
