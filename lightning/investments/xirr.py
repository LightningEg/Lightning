"""Small dependency-free XIRR solver for dated investment cash flows (ACT/365)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def xirr(cashflows: list[tuple[str, Decimal]], as_of: str | None = None) -> Decimal | None:
    """Return annualized XIRR, or None when nonzero dated flows cannot bracket a root.

    A reporting date is not a cash flow: a later as_of must not make same-day flows solvable.
    """
    # XIRR discounts by day, so offsetting same-day entries carry no time-weighted capital.
    # Remove zero daily totals before checking signs/duration to avoid an arbitrary root.
    daily: dict[date, Decimal] = {}
    for day, amount in cashflows:
        if not amount:
            continue
        parsed = date.fromisoformat(day)
        daily[parsed] = daily.get(parsed, Decimal(0)) + amount
    flows = [(day, float(amount)) for day, amount in daily.items() if amount]
    if not any(amount < 0 for _, amount in flows) or not any(amount > 0 for _, amount in flows):
        return None
    origin = min(day for day, _ in flows)
    if max(day for day, _ in flows) == origin:
        return None
    flows = [(day, amount, (day - origin).days / 365.0) for day, amount in flows]

    def npv(rate: float) -> float:
        try:
            return sum(amount / (1.0 + rate) ** years for _, amount, years in flows)
        except (OverflowError, ZeroDivisionError):
            return float("inf")

    # Scan broad rate intervals for a sign change, then bisect to a stable root.
    rates = [-0.999999, -0.99, -0.9, -0.5, 0.0]
    rate = 0.1
    while rate <= 1_000_000:
        rates.append(rate)
        rate = rate * 2 + 0.1
    previous_rate, previous_value = rates[0], npv(rates[0])
    bracket = None
    for current_rate in rates[1:]:
        current_value = npv(current_rate)
        if previous_value == 0:
            return Decimal(str(previous_rate))
        if current_value == 0 or (previous_value < 0) != (current_value < 0):
            bracket = (previous_rate, current_rate)
            break
        previous_rate, previous_value = current_rate, current_value
    if bracket is None:
        return None
    low, high = bracket
    low_value = npv(low)
    for _ in range(160):
        mid = (low + high) / 2
        mid_value = npv(mid)
        if abs(mid_value) < 1e-9 or high - low < 1e-12:
            return Decimal(str(mid))
        if (low_value < 0) != (mid_value < 0):
            high = mid
        else:
            low, low_value = mid, mid_value
    return Decimal(str((low + high) / 2))
