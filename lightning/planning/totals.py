"""Totals the Recurring, Loans, Catch-up and Pay screens show, worked out beside the plan they come from (IT-12AE4).

The screens hand in what they listed (an item with its yearly amount in base currency and its due payments, a
loan's progress); every sum and difference is made here, with the Decimal arithmetic the screens always used."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.core.money import ZERO

from .domain import Payment, PlanKind, PlannedItem


def a_month(per_year: Decimal) -> Decimal:
    """A yearly amount as a month's share of it."""
    return per_year / 12


@dataclass(frozen=True)
class RecurringEntry:
    item: PlannedItem
    per_year: Decimal  # in base currency
    due: Sequence[Payment] = ()


@dataclass(frozen=True)
class RecurringTotals:
    entries: Sequence[RecurringEntry]

    @property
    def subscriptions_per_year(self) -> Decimal:
        return sum((e.per_year for e in self.entries if e.item.kind == PlanKind.SUBSCRIPTION), ZERO)

    @property
    def income_a_month(self) -> Decimal:
        return a_month(sum((e.per_year for e in self.entries if e.item.is_income), ZERO))

    @property
    def due_count(self) -> int:
        return sum(len(e.due) for e in self.entries if not e.item.is_income)

    def due_total(self, planning, day: date) -> Decimal:
        """What the due bills, subscriptions and loan payments come to, in base currency."""
        return sum((planning.amount_in_base(e.item, p.amount, day)
                    for e in self.entries if not e.item.is_income for p in e.due), ZERO)


@dataclass(frozen=True)
class LoanTotals:
    """Every loan together: what was borrowed, what is paid and what is left of it."""
    paid: Decimal
    borrowed: Decimal

    @classmethod
    def of(cls, progress: Iterable[dict]) -> LoanTotals:
        rows = list(progress)
        return cls(sum((p["paid_amount"] for p in rows), ZERO), sum((p["total_amount"] for p in rows), ZERO))

    @property
    def left(self) -> Decimal:
        return self.borrowed - self.paid


def bills_by_category(planning, payments: Iterable[Payment], month: str, day: date) -> dict[int, tuple[Decimal, Decimal]]:
    """A month's scheduled payments by category: what is scheduled and what of it is paid, in base currency."""
    out: dict[int, tuple[Decimal, Decimal]] = {}
    for p in payments:
        if p.due_date[:7] != month:
            continue
        scheduled, paid = out.get(p.item.category_id, (ZERO, ZERO))
        out[p.item.category_id] = (scheduled + planning.amount_in_base(p, p.amount, day),
                                   paid + planning.amount_in_base(p, p.amount - p.still_owed, day))
    return out


def share_of_free_cash(safe_to_spend: Decimal, free_cash: Decimal) -> Decimal:
    """Safe to spend as a percent of free cash (Home's Safe to spend card)."""
    return safe_to_spend / free_cash * 100


def total(amounts: Iterable[Decimal]) -> Decimal:
    """Amounts already in base currency, added up (the payments a catch-up recorded)."""
    return sum(amounts, ZERO)


def reserve_effect(reserve: dict, owed: Decimal) -> dict:
    """What paying ``owed`` takes from a bill's reserve, and what the reserve holds after."""
    used = min(reserve["effective_allocated"], owed)
    return {"name": reserve["name"], "before": reserve["effective_allocated"], "used": used,
            "after": reserve["effective_allocated"] - used}


def budget_effect(line, month: str, owed: Decimal) -> dict:
    """What paying ``owed`` leaves in its category's budget line for the month."""
    after = line.remaining - owed
    return {"name": line.name, "month": month, "left_before": line.remaining, "left_after": after, "over": after < 0}
