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
    planned_actual: Decimal  # spending covered by a limit at this line or below
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
    def target(self) -> Decimal | None:
        """Six months of the chosen average."""
        return self.monthly * 6 if self.monthly else None

    @property
    def top_up(self) -> Decimal:
        """Emergency fund top-up: what the fund lacks to reach its target, spread over
        EMERGENCY_TOP_UP_MONTHS (two years), so a month's plan leaves room to rebuild it."""
        if self.target is None:
            return ZERO
        gap = self.target - (self.set_aside or ZERO)
        return (gap / EMERGENCY_TOP_UP_MONTHS).quantize(Decimal("0.01")) if gap > 0 else ZERO


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
