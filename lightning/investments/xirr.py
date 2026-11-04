"""Bounded, dependency-free XIRR with explicit uncertainty (ACT/365).

In log-rate space NPV is an exponential sum. Its derivative, after removing a
positive exponential factor, has one fewer term. Its zeros partition NPV into
monotone intervals, so two roots within an old scan interval cannot be missed.
Same-day flows are netted exactly before numerical work; ledger arithmetic is
never changed. Numerical limits and near-stationary roots fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from enum import StrEnum
import math


class XirrStatus(StrEnum):
    CONVERGED = "converged"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class XirrResult:
    status: XirrStatus
    rate: Decimal | None = None
    reason: str = ""
    residual: Decimal | None = None


MIN_RATE = Decimal("-0.999999")
MAX_RATE = Decimal("1000000")
RELATIVE_RESIDUAL = Decimal("1e-10")
_MAX_LOG = 512.0
_CRITICAL_TOL = 1e-12
_ROOT_TOL = 1e-13


class _NumericalLimit(Exception):
    pass


@dataclass
class _Budget:
    remaining: int


def _evaluator(times, amounts, budget):
    terms = tuple((t, math.log(abs(a)), 1.0 if a > 0 else -1.0) for t, a in zip(times, amounts))
    def value(x):
        budget.remaining -= len(terms)
        if budget.remaining < 0:
            raise _NumericalLimit("calculation_limit")
        powers = [(log_a - t * x, sign) for t, log_a, sign in terms]
        pivot = max(p for p, _ in powers)
        scaled = [sign * math.exp(p - pivot) for p, sign in powers]
        return math.fsum(scaled) / math.fsum(abs(a) for a in scaled)
    return value


def _tail(value, start, direction, target_sign):
    step = 1.0
    for _ in range(12):
        x = max(-_MAX_LOG, min(_MAX_LOG, start + direction * step))
        y = value(x)
        if y == 0 or (y > 0) == target_sign:
            return x, y
        if abs(x) == _MAX_LOG:
            break
        step *= 2
    raise _NumericalLimit("calculation_limit")


def _bisect(value, low, high, low_value, high_value):
    if low_value == 0:
        return low
    if high_value == 0:
        return high
    for _ in range(160):
        mid = (low + high) / 2
        found = value(mid)
        if abs(found) < _ROOT_TOL or high - low < _ROOT_TOL:
            return mid
        if (low_value > 0) != (found > 0):
            high = mid
        else:
            low, low_value = mid, found
    raise _NumericalLimit("calculation_limit")


def _roots(times, amounts, budget, depth=0):
    changes = sum((a > 0) != (b > 0) for a, b in zip(amounts, amounts[1:]))
    if changes == 0:
        return []
    value = _evaluator(times, amounts, budget)
    if changes == 1:
        # A generalized polynomial with one sign change has exactly one root.
        low, low_value = _tail(value, 0, -1, amounts[-1] > 0)
        high, high_value = _tail(value, 0, 1, amounts[0] > 0)
        return [_bisect(value, low, high, low_value, high_value)]
    if depth >= 128 or len(amounts) > 256:
        raise _NumericalLimit("calculation_limit")
    derivative = [-t * a for t, a in zip(times[1:], amounts[1:])]
    scale = max(abs(a) for a in derivative)
    derivative = [a / scale for a in derivative]
    if any(not a or not math.isfinite(a) for a in derivative):
        raise _NumericalLimit("calculation_limit")
    critical = _roots([t - times[1] for t in times[1:]], derivative, budget, depth + 1)
    points = [None, *critical, None]
    values = [-1.0 if amounts[-1] < 0 else 1.0, *(value(x) for x in critical),
              -1.0 if amounts[0] < 0 else 1.0]
    # A flat zero cannot be distinguished reliably from two very close roots.
    # It must not be certified as a unique rate, or mislabeled as no root.
    if any(abs(y) <= _CRITICAL_TOL for y in values[1:-1]):
        raise _NumericalLimit("unstable_root")
    found = []
    for low, high, low_value, high_value in zip(points, points[1:], values, values[1:]):
        if (low_value > 0) == (high_value > 0):
            continue
        if low is None:
            low, low_value = _tail(value, high if high is not None else 0, -1, low_value > 0)
        if high is None:
            high, high_value = _tail(value, low, 1, high_value > 0)
        found.append(_bisect(value, low, high, low_value, high_value))
    return found


def _verified(flows, rate):
    if not rate.is_finite() or not MIN_RATE <= rate <= MAX_RATE:
        return XirrResult(XirrStatus.UNAVAILABLE, reason="rate_out_of_range")
    origin = flows[0][0]
    with localcontext() as ctx:
        ctx.prec = 60
        discounted = [amount / (1 + rate) ** (Decimal((day - origin).days) / 365) for day, amount in flows]
        residual = sum(discounted, Decimal(0))
        gross = sum((abs(a) for a in discounted), Decimal(0))
        if not gross or abs(residual) > gross * RELATIVE_RESIDUAL:
            return XirrResult(XirrStatus.UNAVAILABLE, reason="residual_too_large")
        return XirrResult(XirrStatus.CONVERGED, rate=rate, residual=residual)


def solve_xirr(cashflows: list[tuple[str, Decimal]], as_of: str | None = None) -> XirrResult:
    """Report one residual-verified rate, multiple roots, or a reason it is unavailable.

    A reporting date contributes no cash flow. Non-conventional histories that
    exceed the numerical work budget, or have a near-stationary root, remain
    unavailable rather than selecting one solution. Reported rates lie within
    MIN_RATE..MAX_RATE; roots outside that display range still count when
    determining ambiguity. Same-day and zero-flow aggregation uses Decimal.
    """
    daily: dict[date, Decimal] = {}
    for day, amount in cashflows:
        if not amount.is_finite():
            return XirrResult(XirrStatus.UNAVAILABLE, reason="invalid_cashflow")
        if amount:
            parsed = date.fromisoformat(day)
            daily[parsed] = daily.get(parsed, Decimal(0)) + amount
    flows = sorted((day, amount) for day, amount in daily.items() if amount)
    if len(flows) < 2 or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return XirrResult(XirrStatus.UNAVAILABLE, reason="insufficient_cashflows")
    try:
        with localcontext() as ctx:
            ctx.prec = 60
            if len(flows) == 2:
                ratio = -flows[1][1] / flows[0][1]
                exponent = Decimal(365) / (flows[1][0] - flows[0][0]).days
                logarithm = ratio.ln() * exponent
                if not (1 + MIN_RATE).ln() <= logarithm <= (1 + MAX_RATE).ln():
                    return XirrResult(XirrStatus.UNAVAILABLE, reason="rate_out_of_range")
                return _verified(flows, ratio ** exponent - 1)
            origin = flows[0][0]
            times = [(day - origin).days / 365.0 for day, _ in flows]
            scale = max(abs(a) for _, a in flows)
            amounts = [float(a / scale) for _, a in flows]
            if any(not a or not math.isfinite(a) for a in amounts):
                raise _NumericalLimit("calculation_limit")
            roots = _roots(times, amounts, _Budget(max(250_000, len(flows) * 256)))
            if len(roots) > 1:
                return XirrResult(XirrStatus.AMBIGUOUS, reason="multiple_roots")
            if not roots:
                return XirrResult(XirrStatus.UNAVAILABLE, reason="no_root")
            return _verified(flows, Decimal(str(roots[0])).exp() - 1)
    except _NumericalLimit as exc:
        return XirrResult(XirrStatus.UNAVAILABLE, reason=str(exc))
    except (ArithmeticError, DecimalException, ValueError):
        return XirrResult(XirrStatus.UNAVAILABLE, reason="calculation_limit")


def xirr(cashflows: list[tuple[str, Decimal]], as_of: str | None = None) -> Decimal | None:
    """Compatibility API: return a rate only for a unique, verified result."""
    return solve_xirr(cashflows, as_of).rate
