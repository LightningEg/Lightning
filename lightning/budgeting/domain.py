"""Budgeting — how much you plan to spend per category per month, against what you actually spent.

Rules
- Budgets exist for money-out categories only (Personal, Work, Fees… and their categories).
- Repeat until changed: an amount set for a month applies to every later month until changed.
  "This month only" overrides a single month.
- Either level: a group budget (Personal 20,000) is the ceiling for everything in the group;
  category budgets (Food 6,000) are part of it. A group without its own amount = sum of its categories.
- Actual = money out in the month for the category and everything under it (refunds reduce it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from lightning.core.money import ZERO


@dataclass
class BudgetEntry:
    """One stored row (see migration 0005)."""

    id: int
    category_id: int
    month: str  # yyyy-mm
    one_off: bool
    amount: Decimal | None  # None = no budget
    average_months: int | None = None  # rolling average from prior complete months
    income_percent: Decimal | None = None


@dataclass
class BudgetLine:
    category_id: int
    code: str
    name: str
    depth: int  # 1 = group (Personal), 2 = category (Food), 3 = sub-category
    direct: Decimal | None  # amount set on this line for the month (None = not set)
    one_off: bool  # the direct amount is a this-month-only override
    average_months: int | None  # None = manual; 3/6 = auto budget from past spending
    budget: Decimal | None  # effective: direct, else sum of children's budgets, else None
    actual: Decimal  # money out, this line and everything under it
    planned_actual: Decimal  # plan-funded spending covered by a limit at this line or below
    covered: bool  # an ancestor has a budget, so this spending is inside a budget
    opening_carryover: Decimal = ZERO
    carryover_enabled: bool = False
    income_percent: Decimal | None = None
    from_loans: bool = False  # planned amount = loan payments scheduled this month (no rule set)
    from_bills: bool = False  # planned amount includes bills and subscriptions scheduled this month

    @property
    def remaining(self) -> Decimal | None:
        return None if self.budget is None else self.budget + self.opening_carryover - self.planned_actual

    @property
    def available(self) -> Decimal | None:
        return None if self.budget is None else self.budget + self.opening_carryover

    @property
    def over(self) -> bool:
        return self.available is not None and self.planned_actual > self.available


@dataclass
class BudgetSection:
    name: str  # Personal / Work
    lines: list[BudgetLine] = field(default_factory=list)
    unbudgeted: Decimal = ZERO  # money out in categories with no budget on them or above them
    one_off: Decimal = ZERO  # money out in one-off categories: in cash flow, outside the budget

    @property
    def groups(self) -> list[BudgetLine]:
        return [line for line in self.lines if line.depth == 1]

    @property
    def budget(self) -> Decimal:
        return sum((g.budget or ZERO for g in self.groups), ZERO)

    @property
    def actual(self) -> Decimal:
        return sum((g.actual for g in self.groups), ZERO)

    @property
    def planned_actual(self) -> Decimal:
        """Spending covered by category or ancestor limits."""
        return sum((group.planned_actual for group in self.groups), ZERO)

    @property
    def remaining(self) -> Decimal:
        return self.available - self.planned_actual

    @property
    def available(self) -> Decimal:
        return sum((g.available or ZERO for g in self.groups), ZERO)



@dataclass
class BudgetMonth:
    month: str
    sections: list[BudgetSection]
    income: Decimal  # money in this month, for context
    warnings: list[str]

    @property
    def budget(self) -> Decimal:
        return sum((s.budget for s in self.sections), ZERO)

    @property
    def actual(self) -> Decimal:
        return sum((s.actual for s in self.sections), ZERO)

    @property
    def remaining(self) -> Decimal:
        return sum((section.remaining for section in self.sections), ZERO)

    @property
    def available(self) -> Decimal:
        return sum((s.available for s in self.sections), ZERO)

    @property
    def unbudgeted(self) -> Decimal:
        return sum((s.unbudgeted for s in self.sections), ZERO)

    @property
    def one_off(self) -> Decimal:
        return sum((s.one_off for s in self.sections), ZERO)


# IT-12AE4: a plan's derived figures, for the screens that read a plan summary rather than a BudgetMonth.
def left_in_plan(planned: Decimal, spent: Decimal) -> Decimal:
    """Left in plan: Planned less Spent (below zero when over)."""
    return planned - spent


def used_of_plan(planned: Decimal, left: Decimal) -> Decimal:
    """What a plan has used: Planned less Left in plan."""
    return planned - left


def over_plan_by(spent: Decimal, planned: Decimal) -> Decimal:
    """How far spending went past the plan: Spent less Planned."""
    return spent - planned


def share_of_plan(amount: Decimal, planned: Decimal) -> Decimal:
    """An amount as a percentage of Planned (the caller checks there is a plan)."""
    return amount / planned * 100


def left_per_day(left: Decimal, days_left: int) -> Decimal:
    """Left in plan spread over the days left, today included (the caller checks there are days)."""
    return left / days_left


def over_plan_total(overs: list[Decimal]) -> Decimal:
    """Categories' overspends added up: Over plan."""
    return sum(overs, ZERO)


def spent_outside(total: Decimal, by_category: list[Decimal]) -> Decimal:
    """Spending the listed categories leave out: the total less what they spent (a category under zero counts nothing)."""
    return total - sum((value for value in by_category if value > 0), ZERO)


@dataclass(frozen=True)
class IncomeAverage:
    """Average monthly income, and the completed months it was averaged over."""
    amount: Decimal | None
    months_counted: int        # completed months in the window that had income
    lookback: int              # 3 or 6, from Settings
    first_month: str           # yyyy-mm, the window (empty for a manual amount)
    last_month: str
    manual: bool = False
    scheduled: bool = False    # no completed month had income yet: Recurring income stands in

    @property
    def window(self) -> str:
        if self.scheduled:
            return "from your recurring income"
        return f"{self.first_month} to {self.last_month}" if self.first_month else ""



@dataclass(frozen=True)
class SpendingAverage:
    """Average monthly spending, and the completed months it was averaged over."""
    amount: Decimal | None
    months_counted: int        # completed months in the window that had spending
    lookback: int              # 3 or 6, the same as Average monthly income
    first_month: str           # yyyy-mm, the window
    last_month: str

    @property
    def window(self) -> str:
        return f"{self.first_month} to {self.last_month}" if self.first_month else ""


EMERGENCY_BASES = {"income": "average_monthly_income", "spending": "average_monthly_spending"}


INCOME_FROM_RECURRING = "budget_income_from_recurring"  # setting: "1" plans with Recurring income, not the average
EMERGENCY_TOP_UP_MONTHS = 24  # owner request 2026-10-05: reach six months within two years


@dataclass(frozen=True)
class EmergencyFund:
    """How long the emergency fund lasts, in months of Average monthly income or of Average monthly
    spending, whichever Settings › Budget names. The aim is six months."""
    set_aside: Decimal | None              # None while there is no emergency fund
    basis: str                             # a key of EMERGENCY_BASES
    average: IncomeAverage | SpendingAverage
    # BT-7AV1 (owner, 2026-11-14): the month's ask is fixed on the 1st. ``start`` is what was set aside then (None:
    # unknown, the ask follows today's balance); ``moved`` is what went in since, which the month's ask counts.
    start: Decimal | None = None
    moved: Decimal = ZERO

    @property
    def figure(self) -> str:
        """The registry key of the average it is counted in."""
        return EMERGENCY_BASES[self.basis]

    @property
    def monthly(self) -> Decimal | None:
        amount = self.average.amount
        return amount if amount and amount > 0 else None

    @property
    def months(self) -> Decimal | None:
        return self.set_aside / self.monthly if self.set_aside is not None and self.monthly else None

    @property
    def working(self):
        """NF-12AB2: months covered is what is set aside over the chosen monthly average."""
        from lightning.core.working import Working, WorkingRow
        set_aside = self.set_aside or ZERO
        return Working("emergency_fund", self.months, (WorkingRow("Set aside", set_aside, "/plan/reserves"),),
                       home="/plan/reserves", ratio_of=(set_aside, self.monthly or ZERO))

    @property
    def target(self) -> Decimal | None:
        """Six months of the chosen average."""
        return self.monthly * 6 if self.monthly else None

    def _share(self, set_aside: Decimal | None) -> Decimal:
        if self.target is None:
            return ZERO
        gap = self.target - (set_aside or ZERO)
        return (gap / EMERGENCY_TOP_UP_MONTHS).quantize(Decimal("0.01")) if gap > 0 else ZERO

    @property
    def top_up(self) -> Decimal:
        """Emergency fund top-up, this month's: what the fund lacked on the 1st to reach its target, spread over
        EMERGENCY_TOP_UP_MONTHS (two years), less what was moved in since, never below zero (BT-7AV1). Doing what
        the plan asked therefore leaves Safe to spend where it was; money taken out shows from next month."""
        if self.start is None:
            return self.ongoing_top_up
        return max(self._share(self.start) - self.moved, ZERO)

    @property
    def ongoing_top_up(self) -> Decimal:
        """The top-up a later month asks, from what is set aside today."""
        return self._share(self.set_aside)


@dataclass(frozen=True)
class BudgetFillRow:
    """One read-only row offered by a month-fill source."""

    category_id: int | None
    category_name: str
    source: str
    amount: Decimal | None
    current_amount: Decimal | None = None
    current_rule: str = ""
    conflict: str = ""
    selectable: bool = True
    selected: bool = False
    already_using_last_month: bool = False
    note: str = ""


@dataclass(frozen=True)
class BudgetFillProposal:
    month: str
    source: str
    rows: tuple[BudgetFillRow, ...]


class ScheduleView(Protocol):
    """What the plan has scheduled, as Budget reads it: one read-only view that Planning builds for a request and
    passes into every budget call that needs it (Budgeting is below Planning and never imports it)."""

    def loans(self, month: str) -> dict[int, Decimal]:
        """Loan payments scheduled in the month, by spending category."""

    def bills(self, month: str) -> dict[int, dict]:
        """Bills and subscriptions due in the month, by category: {"amount", "items"}."""

    def income(self) -> Decimal | None:
        """Income a month that Cash planning › Recurring expects; None without any."""

    def goal_needs(self, month: str) -> list[dict]:
        """What dated reserve goals still need saved each month, from the month on."""
