from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from lightning.core.money import ZERO

from .dated_cash import DatedCashForecast


class PlanKind(StrEnum):
    BILL = "BILL"
    SUBSCRIPTION = "SUBSCRIPTION"
    INCOME = "INCOME"
    LOAN = "LOAN"


KIND_LABELS = {PlanKind.BILL: "Bill", PlanKind.SUBSCRIPTION: "Subscription",
               PlanKind.INCOME: "Income", PlanKind.LOAN: "Loan"}
RECURRING_KINDS = (PlanKind.BILL, PlanKind.SUBSCRIPTION, PlanKind.INCOME)


class Frequency(StrEnum):
    ONCE = "ONCE"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


FREQUENCY_LABELS = {Frequency.ONCE: "Once", Frequency.WEEKLY: "Weekly", Frequency.MONTHLY: "Monthly",
                    Frequency.QUARTERLY: "Every 3 months", Frequency.YEARLY: "Yearly"}


class WeekendMove(StrEnum):
    """Where a payment that falls on Friday or Saturday goes."""
    NONE = "none"
    BEFORE = "before"   # Thursday: Egyptian payroll pays before the weekend
    AFTER = "after"     # Sunday


WEEKEND_MOVE_LABELS = {WeekendMove.NONE: "Keep", WeekendMove.BEFORE: "Day before", WeekendMove.AFTER: "Day after"}


class PaymentStatus(StrEnum):
    PAID = "PAID"          # settled by a posted transaction
    SKIPPED = "SKIPPED"    # the user says this one will not happen
    DUE = "DUE"            # date is today or earlier and nothing settled it
    UPCOMING = "UPCOMING"  # date is after today


@dataclass(frozen=True)
class PlannedItem:
    id: int
    kind: PlanKind
    name: str
    amount: Decimal                 # per payment, always positive
    frequency: Frequency
    interval_count: int
    start_date: str
    end_date: str | None
    payment_count: int | None
    account_id: int | None
    category_id: int | None
    counterparty_id: int | None
    principal: Decimal | None
    active: bool
    notes: str
    weekend_move: WeekendMove = WeekendMove.NONE
    month_day: int | None = None
    match_window_days: int = 7
    match_tolerance_pct: int = 10

    @property
    def is_income(self) -> bool:
        return self.kind == PlanKind.INCOME

    @property
    def kind_label(self) -> str:
        return KIND_LABELS[self.kind]


def per_year(item: PlannedItem) -> Decimal:
    """What a repeating item comes to in a year; a one-off payment comes to nothing a year."""
    times = {Frequency.ONCE: 0, Frequency.WEEKLY: Decimal(52), Frequency.MONTHLY: Decimal(12),
             Frequency.QUARTERLY: Decimal(4), Frequency.YEARLY: Decimal(1)}[item.frequency]
    return (item.amount * times / item.interval_count).quantize(Decimal("0.01")) if times else ZERO


@dataclass(frozen=True)
class Payment:
    """One scheduled payment of a planned item and its status on the as-of date."""
    item: PlannedItem
    due_date: str
    number: int                     # 1-based position in the schedule
    status: PaymentStatus
    transaction_id: int | None = None
    paid_amount: Decimal | None = None  # what was actually paid, when it was recorded or linked
    amount_override: Decimal | None = None

    @property
    def amount(self) -> Decimal:
        return self.item.amount if self.amount_override is None else self.amount_override

    def days_late(self, as_of) -> int:
        """Whole days past its date while it is still unpaid (0 when due today or later, or settled)."""
        if not self.outstanding:
            return 0
        return max((as_of - date.fromisoformat(self.due_date)).days, 0)

    @property
    def outstanding(self) -> bool:
        return self.status in (PaymentStatus.DUE, PaymentStatus.UPCOMING) or (
            self.item.kind == PlanKind.LOAN and self.status == PaymentStatus.PAID
            and self.paid_amount is not None and self.paid_amount < self.amount)

    @property
    def still_owed(self) -> Decimal:
        """What is left of this payment: all of it while outstanding, and the shortfall of a payment
        recorded for less than its amount (a partial loan instalment is not a full one)."""
        if self.item.kind == PlanKind.LOAN and self.status == PaymentStatus.PAID and self.paid_amount is not None:
            return max(self.amount - self.paid_amount, Decimal(0))
        if self.outstanding:
            return self.amount
        return Decimal(0)


@dataclass(frozen=True)
class WhatYouOwe:
    bills_due: Decimal              # unpaid bills, subscriptions and loan payments dated on or before as-of
    loans_still_to_pay: Decimal     # every unpaid loan payment, due or upcoming
    bills_due_items: list[Payment] = field(default_factory=list)
    loans_due_in_base: Decimal | None = None

    @property
    def other_bills_due_items(self) -> list[Payment]:
        """The bills due that are not loan payments, oldest first."""
        return [p for p in self.bills_due_items if p.item.kind != PlanKind.LOAN]

    @property
    def other_bills_due(self) -> Decimal:
        """Bills due that are not loan payments (those are already in loans still to pay)."""
        return self.bills_due - (self.loans_due_in_base if self.loans_due_in_base is not None else
                                 sum((p.still_owed for p in self.bills_due_items if p.item.kind == PlanKind.LOAN), ZERO))

    @property
    def total(self) -> Decimal:
        """What you owe: bills due plus loans still to pay, each payment counted once."""
        return self.other_bills_due + self.loans_still_to_pay


@dataclass(frozen=True)
class ForecastMonth:
    month: str
    opening: Decimal
    income: Decimal
    income_estimated: bool          # True when Average monthly income stands in for scheduled income
    commitments: Decimal            # bills, subscriptions and loan payments scheduled in the month
    budget_spending: Decimal        # remaining budget plan not already covered by scheduled bills
    goal_saving: Decimal            # what reserves with due dates still need this month
    closing: Decimal
    deposit_cash: Decimal = ZERO
    emergency_saving: Decimal = ZERO  # Emergency fund top-up: what the plan check asks the month to leave for it
    target_saving: Decimal = ZERO     # Rest of savings target: what the target asks beyond goals and the top-up
    circle_in: Decimal = ZERO         # gam'eya payout (and estimated interest) landing in the month
    circle_out: Decimal = ZERO        # gam'eya instalments falling in the month

    @property
    def money_in(self) -> Decimal:
        return self.income + self.deposit_cash + self.circle_in

    @property
    def money_out(self) -> Decimal:
        return (self.commitments + self.budget_spending + self.goal_saving + self.emergency_saving
                + self.target_saving + self.circle_out)

    @property
    def net(self) -> Decimal:
        return self.money_in - self.money_out


@dataclass(frozen=True)
class EverydayBudget:
    """A month's plan split into the bills it holds and the everyday money around them (guideline 3.32 A08.3,
    owner 2026-10-19: Budget's day rate counts everyday money only). Plan only: it moves no money."""
    month: str
    planned: Decimal                 # Planned: the Budget screen's plan (BudgetService.plan_summary)
    spent: Decimal                   # Spent of the plan, bills included
    left: Decimal                    # Left in plan
    bills_to_pay: Decimal            # bills and loan payments in planned categories not paid yet
    everyday_left: Decimal           # Left in plan less bills to pay: Budget until payday's own figure this month
    everyday_plan: Decimal           # Planned less the bills and loan payments scheduled in planned categories
    everyday_spent: Decimal          # Spent less payments marked paid against a bill or loan
    day: int                         # days of the month counted so far (all of a past month, 0 for a future one)
    days_in_month: int
    current: bool                    # the month holds today
    by_day: list[Decimal]            # everyday spending so far, added up day by day (index 0 is day 1)
    last_month_by_day: list[Decimal]  # the same for the month before, every day of it
    room: dict[int, Decimal] = field(default_factory=dict)  # each planned category's left less its bills to pay
    payments: list = field(default_factory=list)  # bill and loan payments in planned categories: the month's, and earlier unpaid ones

    @property
    def days_left(self) -> int:
        return self.days_in_month - self.day + 1 if self.current else 0

    @property
    def per_day(self) -> Decimal | None:
        """Everyday money left for each day still to come, today included."""
        return (self.everyday_left / self.days_left).quantize(Decimal("0.01")) if self.days_left > 0 else None

    @property
    def pace(self) -> Decimal:
        """What the everyday plan allows by today, spread evenly over the month."""
        return (self.everyday_plan * self.day / self.days_in_month).quantize(Decimal("0.01")) if self.days_in_month else ZERO

    @property
    def last_month_same_day(self) -> Decimal | None:
        """The month before's everyday spending by the same day of the month (its last day when shorter)."""
        if not self.last_month_by_day or not self.day:
            return None
        return self.last_month_by_day[min(self.day, len(self.last_month_by_day)) - 1]


@dataclass(frozen=True)
class CashForecast:
    as_of: str
    free_cash: Decimal
    average_income: Decimal | None
    average_income_months: int
    next_income_date: str | None
    next_income_estimated: bool
    safe_to_spend: Decimal
    safe_to_spend_parts: list[tuple[str, Decimal]]
    months: list[ForecastMonth]
    upcoming: list[Payment]
    # The payments Safe to spend takes off: scheduled, not yet due, before the next income.
    payments_before_income: list[Payment] = field(default_factory=list)
    dated: DatedCashForecast | None = None
    # Due before payday: what is still owed on those payments, in the profile currency (the part Safe to spend takes off).
    payments_before_income_total: Decimal = Decimal(0)

    @property
    def first_short_month(self) -> ForecastMonth | None:
        """The first forecast month that ends below your reserves (free cash under zero), if any."""
        return next((m for m in self.months if m.closing < 0), None)

    @property
    def lowest(self) -> ForecastMonth | None:
        return min(self.months, key=lambda m: m.closing) if self.months else None
