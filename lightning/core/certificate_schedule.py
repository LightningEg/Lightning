"""A certificate's interest the way the bank pays it, as pure functions of its terms (no database).

``periods`` lists each interest period from purchase to maturity with what it earns; the payout schedule
(``events``) and the value earned to date (``accrued``) both read it, so the forecast, the holding's value and the
maturity amount always agree.

IV-12J4: a variable certificate's rate changes are dated. ``rates`` is a list of ``(effective date, annual rate)``;
each period earns at the rate in force on its first day (the purchase rate until the first change).
IV-12J3: a certificate that pays at maturity (simple at maturity, or compound) is worth its principal plus the
interest earned so far, an estimate from its terms; the redemption then records what the bank actually paid.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from lightning.core.dates import add_months
from lightning.core.money import ZERO


_MICRO = Decimal("0.000001")
# Keyed by the stored values; the enums in lightning/deposits/domain.py are StrEnums of the same text. This module
# sits in core so reporting (valuation) and deposits (forecast) share it without reporting importing deposits.
PAYOUT_MONTHS = {"MONTHLY": 1, "QUARTERLY": 3, "YEARLY": 12}
COMPOUND_MONTHS = {"MONTHLY": 1, "QUARTERLY": 3, "YEARLY": 12}


@dataclass(frozen=True)
class Period:
    begin: date
    end: date
    rate: Decimal      # percentage points in force for this period
    interest: Decimal  # unrounded; compound periods earn on the principal plus what earlier periods added


def whole_months(start: date, end: date) -> int:
    """The number of whole months from start to end, or 0 when end is not a whole number of months away."""
    months = (end.year - start.year) * 12 + end.month - start.month
    return months if months > 0 and add_months(start, months) == end else 0


def period_interest(principal: Decimal, rate: Decimal, begin: date, end: date, months: int) -> Decimal:
    """IV-12J2: interest for one payout period the way Egyptian banks pay it. A full period of ``months`` months earns
    principal x rate x months / 12 (a monthly payout is the same every month); a broken period (``months`` 0, shorter
    than its schedule) earns by actual days / 365. ``rate`` is a fraction (0.22 for 22%)."""
    if months:
        return principal * rate * Decimal(months) / Decimal(12)
    return principal * rate * Decimal((end - begin).days) / Decimal(365)


def rate_on(terms, rates, day: date) -> Decimal:
    """The annual rate (percentage points) in force on ``day``: the latest dated change on or before it, else the
    rate the certificate was bought at."""
    found = terms.annual_rate
    for when, rate in sorted(rates or ()):
        if when <= day:
            found = rate
    return found


def pays_at_maturity(terms) -> bool:
    """Interest that stays with the bank until maturity, so the certificate's value grows as it is earned."""
    return terms.interest_method == "COMPOUND" or terms.payout_frequency == "AT_MATURITY"


def periods(terms, rates=()) -> list[Period]:
    start, maturity = date.fromisoformat(terms.start_date), date.fromisoformat(terms.maturity_date)
    principal = terms.principal
    compound = terms.interest_method == "COMPOUND"
    if not compound and terms.payout_frequency == "AT_MATURITY":
        rate = rate_on(terms, rates, start)
        return [Period(start, maturity, rate, period_interest(principal, rate / 100, start, maturity,
                                                              whole_months(start, maturity)))]
    step = COMPOUND_MONTHS[terms.compounding_frequency] if compound else PAYOUT_MONTHS[terms.payout_frequency]
    out, previous, index, added = [], start, 1, ZERO
    while True:
        boundary = add_months(start, index * step)
        period_end = min(boundary, maturity)
        rate = rate_on(terms, rates, previous)
        interest = period_interest(principal + added, rate / 100, previous, period_end,
                                   step if period_end == boundary else 0)
        out.append(Period(previous, period_end, rate, interest))
        if compound:
            added += interest
        previous = period_end
        if period_end == maturity:
            return out
        index += 1


def events(terms, rates=()) -> list[tuple[date, Decimal, str]]:
    """Every payment the bank makes over the certificate's life: (date, amount rounded to 6 places, kind) with kind
    INTEREST, PRINCIPAL or MATURITY (a compound certificate pays principal and interest together)."""
    found = periods(terms, rates)
    maturity = date.fromisoformat(terms.maturity_date)

    def q(amount: Decimal) -> Decimal:
        return amount.quantize(_MICRO, rounding=ROUND_HALF_UP)

    if terms.interest_method == "COMPOUND":
        return [(maturity, q(terms.principal + sum((p.interest for p in found), ZERO)), "MATURITY")]
    return [*((p.end, q(p.interest), "INTEREST") for p in found), (maturity, q(terms.principal), "PRINCIPAL")]


def accrued(terms, day: date, rates=()) -> Decimal:
    """Interest earned by ``day`` and not yet paid out, for a certificate that pays at maturity (zero for one that
    pays as it goes, whose interest reaches the bank account instead). Each period's interest is earned evenly over
    its days, so the value rises smoothly and reaches the maturity amount on the maturity day."""
    if not pays_at_maturity(terms):
        return ZERO
    total = ZERO
    for p in periods(terms, rates):
        if day >= p.end:
            total += p.interest
        elif day > p.begin:
            total += p.interest * Decimal((day - p.begin).days) / Decimal((p.end - p.begin).days)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
