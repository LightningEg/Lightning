"""One state per payment for a day, and the catch-up state (IV-3AY5).

Four screens used to count the same bills with four windows (Needs you 3 days, More 14 days, What you owe "due
today or late", the forecast "before payday"). Each now reads the rows below; a screen picks the states it
shows. Money is never worked out here: amounts come from the planning service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from lightning.core.dates import fmt_date, parse_date
from lightning.planning.domain import Payment, PaymentStatus, PlanKind

STALE_DAYS = 7      # late for longer than this, or due before the last payday: one catch-up question, not a row each
SOON_DAYS = 3       # due today or within three days (guideline C04.4)
AWAY_DAYS = 3       # nothing recorded for this long: the catch-up state (C13)
BILL_KINDS = (PlanKind.BILL, PlanKind.SUBSCRIPTION, PlanKind.LOAN)


class BillState(StrEnum):
    LATE_STALE = "late_stale"        # late more than STALE_DAYS, or due before the last payday
    LATE = "late"                    # past its date
    DUE_SOON = "due_soon"            # today or within SOON_DAYS
    BEFORE_PAYDAY = "before_payday"  # later than that, but before the next income
    LATER = "later"                  # after the next income
    PAID = "paid"
    SKIPPED = "skipped"


NEEDS_ACTION = (BillState.LATE_STALE, BillState.LATE, BillState.DUE_SOON)


@dataclass(frozen=True)
class BillRow:
    payment: Payment
    state: BillState
    late_days: int
    days_until: int  # 0 when late or due today

    @property
    def due_date(self) -> str:
        return self.payment.due_date


def next_income_date(planning, day: date) -> str | None:
    """The date of the next scheduled income after ``day``, as the forecast reads it (None when none is planned)."""
    early = {(e["item"].id, e["payment"].due_date) for e in planning.early_payments(day)}
    upcoming = [p for p in planning.all_payments(day + timedelta(days=62), day, (PlanKind.INCOME,))
                if p.outstanding and p.due_date > fmt_date(day) and (p.item.id, p.due_date) not in early]
    return upcoming[0].due_date if upcoming else None


def last_income_date(planning, day: date) -> str | None:
    """The date of the latest scheduled income already received on or before ``day``."""
    received = [p.due_date for item in planning.items((PlanKind.INCOME,))
                for p in planning.payments(item, fmt_date(day), day) if p.status == PaymentStatus.PAID]
    return max(received) if received else None


def state_of(payment: Payment, day: date, next_income: str | None, last_income: str | None) -> BillState:
    if payment.status == PaymentStatus.SKIPPED:
        return BillState.SKIPPED
    if not payment.outstanding:
        return BillState.PAID
    late = payment.days_late(day)
    if late:
        stale = late > STALE_DAYS or bool(last_income and payment.due_date < last_income)
        return BillState.LATE_STALE if stale else BillState.LATE
    days = (parse_date(payment.due_date) - day).days
    if days <= SOON_DAYS:
        return BillState.DUE_SOON
    if next_income and payment.due_date < next_income:
        return BillState.BEFORE_PAYDAY
    return BillState.LATER


def open_bills(planning, day: date, horizon_days: int = 14, kinds=BILL_KINDS) -> list[BillRow]:
    """Every unpaid payment of ``kinds`` that is late or due within ``horizon_days``, earliest first."""
    nxt, last = next_income_date(planning, day), last_income_date(planning, day)
    rows = []
    for p in planning.all_payments(day + timedelta(days=horizon_days), day, kinds):
        if not p.outstanding:
            continue
        rows.append(BillRow(p, state_of(p, day, nxt, last), p.days_late(day),
                            max((parse_date(p.due_date) - day).days, 0)))
    return rows


@dataclass(frozen=True)
class CatchUp:
    days_since_entry: int | None  # None: nothing recorded yet
    stale_bills: int
    away: bool


def catch_up(c, day: date, rows: list[BillRow] | None = None) -> CatchUp:
    """Whether the person has been away: nothing recorded for AWAY_DAYS, or bills late for longer than STALE_DAYS.
    A bulk import or a sample load is one recording moment (the ledger's created_at, to the minute)."""
    last = c.db.scalar("SELECT MAX(created_at) FROM transactions WHERE status='POSTED' AND type NOT IN ('VAL','OPN')")
    since = max((day - date.fromisoformat(last[:10])).days, 0) if last else None
    stale = sum(1 for r in (rows if rows is not None else open_bills(c.planning, day)) if r.state == BillState.LATE_STALE)
    return CatchUp(since, stale, bool((since is not None and since >= AWAY_DAYS) or stale))
