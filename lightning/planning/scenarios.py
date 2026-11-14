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
    scenario_plan_low: object = None  # the same, with the change, on its lowest day: (month, value, date)
    months: tuple = ()            # every month as (month, plan closing, scenario's lowest day in it or None)

    @property
    def change(self):
        """IV-12Q2: what the scenario does to the plan's Lowest point ahead (None without both)."""
        if self.plan_low is None or self.scenario_plan_low is None:
            return None
        return self.scenario_plan_low[1] - self.plan_low.closing

    @property
    def first_below_zero(self):
        """BV-7AW: the first day the plan, with the change, goes below zero: (date, value), or None."""
        return next(((on, value) for _, _, _, days in self._days for on, value in days if value is not None and value < 0), None)

    _days: tuple = ()  # (month, plan closing, lowest, ((date, value), ...)) for each month, in order


def _balance_on(projection, on: str):
    """Day-end combined scheduled cash on ``on``: the last point on or before it (None when FX is missing)."""
    known = [row for row in projection.balances if row.date <= on]
    return known[-1].balance if known else None


def plan_days(forecast, baseline, projected, day, end):
    """BV-7AW (r37 W3, M2): one measure for the whole page. Each day of a month is that month's planned closing (Cash
    planning's month end) moved by what the scenario changes in scheduled cash on that day, so a salary 20 days late
    inside one month shows as the dip it is, not only at month ends. Days after ``end`` keep the change at ``end``.
    Returns (month, plan closing, lowest (date, value) or None, ((date, value), ...)) per month; a value is None when
    an exchange rate is missing."""
    from lightning.core.dates import parse_month
    points = sorted({row.date for row in baseline.balances} | {row.date for row in projected.balances})
    start, stop = day.isoformat(), end.isoformat()
    rows = []
    for month in forecast.months:
        first, last = parse_month(month.month)
        lo, hi = max(first.isoformat(), start), min(last.isoformat(), stop)
        dates = sorted({d for d in points if lo <= d <= hi} | {min(last.isoformat(), stop) if lo <= hi else stop})
        days = []
        for on in dates:
            before, after = _balance_on(baseline, on), _balance_on(projected, on)
            days.append((on, None if before is None or after is None else month.closing + after - before))
        known = [row for row in days if row[1] is not None]
        lowest = min(known, key=lambda row: row[1]) if len(known) == len(days) and known else None
        rows.append((month.month, month.closing, lowest, tuple(days)))
    return tuple(rows)


def plan_months(forecast, baseline, projected, end, day=None):
    """Each month of the cash forecast as (month, plan closing, the scenario's lowest day in it or None)."""
    from lightning.core.dates import today
    days = plan_days(forecast, baseline, projected, day or today(), end)
    return tuple((month, closing, low[1] if low else None) for month, closing, low, _ in days)


def plan_lowest(forecast, baseline, projected, end, day=None):
    """IV-12P, BV-7AW: the plan's Lowest point ahead, and the same with the scenario on its lowest day. Returns
    (baseline month, (month, value, date)) or (None, None) without a forecast, (low, None) when a rate is missing."""
    from lightning.core.dates import today
    low = forecast.lowest
    if low is None:
        return None, None
    rows = plan_days(forecast, baseline, projected, day or today(), end)
    if any(lowest is None for _, _, lowest, _ in rows):
        return low, None
    month, _, (on, value), _ = min(rows, key=lambda row: row[2][1])
    return low, (month, value, on)


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
    plan_low, scenario_plan_low = plan_lowest(forecast, baseline, projected, end, day)
    days = plan_days(forecast, baseline, projected, day, end)
    months = tuple((month, closing, low[1] if low else None) for month, closing, low, _ in days)
    return ScenarioResult(baseline, projected, lowest_scheduled_balance(baseline), lowest_scheduled_balance(projected),
                          tuple(assumptions), plan_low, scenario_plan_low, months, days)
