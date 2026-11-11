"""Scheduled-cash scenario comparisons. Pure projections over confirmed ledger inputs.

No income average or historical spending is invented. Overdue income remains excluded unless
its one outstanding occurrence is explicitly moved to a future date. Plans are never saved.
"""
from dataclasses import dataclass, replace
from datetime import timedelta

from lightning.core.dates import parse_date
from lightning.core.errors import ValidationError
from lightning.core.money import to_decimal
from .dated_cash import dated_cash_forecast, lowest_scheduled_balance
from .domain import PlanKind


@dataclass(frozen=True)
class ScenarioResult:
    baseline: object
    scenario: object
    baseline_low: object
    scenario_low: object
    assumptions: tuple[str, ...]
    plan_low: object = None       # IV-12P: Cash planning's Lowest point ahead (a ForecastMonth), as the plan shows it
    scenario_plan_low: object = None  # the same months moved by what the scenario changes: (month, closing)
    months: tuple = ()            # IV-12Q2: every month as (month, plan closing, scenario closing or None), for the chart


def _balance_on(projection, on: str):
    """Day-end combined scheduled cash on ``on``: the last point on or before it (None when FX is missing)."""
    known = [row for row in projection.balances if row.date <= on]
    return known[-1].balance if known else None


def plan_months(forecast, baseline, projected, end):
    """IV-12Q2: each month of the cash forecast as (month, plan closing, scenario closing), the scenario closing moved
    by the scenario's change in scheduled cash at the month's end (None when an exchange rate is missing)."""
    from lightning.core.dates import parse_month
    rows = []
    for month in forecast.months:
        _, last = parse_month(month.month)
        on = min(last, end).isoformat()
        before, after = _balance_on(baseline, on), _balance_on(projected, on)
        moved = None if before is None or after is None else month.closing + after - before
        rows.append((month.month, month.closing, moved))
    return tuple(rows)


def plan_lowest(forecast, baseline, projected, end):
    """IV-12P: the plan's Lowest point ahead, with and without the scenario. Each month of the cash forecast keeps its
    closing and moves by the scenario's change in scheduled cash at that month's end (at ``end`` for months after it,
    where a purchase stays spent and a delayed income has arrived). Returns (baseline month, (month, closing)) or
    (None, None) without a forecast or when an exchange rate is missing."""
    low = forecast.lowest
    if low is None:
        return None, None
    moved = [(month, closing) for month, _, closing in plan_months(forecast, baseline, projected, end)]
    if any(closing is None for _, closing in moved):
        return low, None
    return low, min(moved, key=lambda row: row[1])


def occurrence_key(payment):
    return f'{payment.item.id}:{payment.due_date}'


def available_inputs(forecaster, day, end):
    payments, events = forecaster.scheduled_inputs(day, end)
    return payments, events


def compare_scenario(forecaster, day, end, *, income='', delay='', purchase='', purchase_date='',
                     account_id='', bill='', bill_amount=''):
    payments, events = available_inputs(forecaster, day, end)
    changed, changed_events = list(payments), list(events)
    assumptions = []
    if income:
        selected = next((p for p in payments if occurrence_key(p) == income and p.item.is_income), None)
        try:
            days = int(delay)
        except (ValueError, TypeError):
            days = 0
        if selected is None or not 1 <= days <= 90:
            raise ValidationError('Choose outstanding income and a delay of 1 to 90 days.')
        shifted = parse_date(selected.due_date) + timedelta(days=days)
        if shifted < day or shifted > end:
            raise ValidationError('The delayed income date must be inside the comparison period.')
        changed = [replace(p, due_date=shifted.isoformat()) if p is selected else p for p in changed]
        assumptions.append(f'{selected.item.name}: {selected.due_date} → {shifted.isoformat()}')
    if bill:
        selected = next((p for p in payments if occurrence_key(p) == bill and p.item.kind in (PlanKind.BILL, PlanKind.SUBSCRIPTION)), None)
        value = to_decimal(bill_amount, 'bill_amount')
        if selected is None or value < 0:
            raise ValidationError('Choose an outstanding bill and a nonnegative amount.')
        changed = [replace(p, amount_override=value) if p is selected else p for p in changed]
        assumptions.append(f'{selected.item.name}: {selected.amount:f} → {value:f}')
    if purchase:
        value = to_decimal(purchase, 'purchase')
        when = parse_date(purchase_date, 'purchase_date')
        try:
            account = forecaster.reporting.accounts.get(int(account_id))
        except (ValueError, TypeError):
            raise ValidationError('Choose the cash account for this purchase.') from None
        if value <= 0 or not day <= when <= end or not account.active or account.account_type.value not in ('CASH', 'BANK', 'BROKERAGE'):
            raise ValidationError('Choose a positive purchase, a cash account and a date inside the comparison period.')
        from lightning.deposits.domain import DepositEvent
        changed_events.append(DepositEvent(when.isoformat(), account.id, -value, 'SCENARIO', 0))
        assumptions.append(f'{account.name}: −{value:f} {account.currency} · {when.isoformat()}')
    baseline = dated_cash_forecast(forecaster.reporting, payments, events, day, end)
    projected = dated_cash_forecast(forecaster.reporting, changed, changed_events, day, end)
    forecast = forecaster.forecast(day, match_payments=False)
    plan_low, scenario_plan_low = plan_lowest(forecast, baseline, projected, end)
    return ScenarioResult(baseline, projected, lowest_scheduled_balance(baseline), lowest_scheduled_balance(projected),
                          tuple(assumptions), plan_low, scenario_plan_low, plan_months(forecast, baseline, projected, end))
