"""Return shown to a person: actual gain under a year, dated annual return after it."""
from dataclasses import dataclass
from decimal import Decimal

from lightning.core.dates import parse_date
from lightning.core.money import ZERO
from .xirr import XirrResult, XirrStatus


_EXPLANATIONS = {
    "multiple_roots": "More than one annualized return fits these cash flows.",
    "no_root": "These cash flows have no annualized return.",
    "insufficient_cashflows": "Not enough dated cash flows to calculate an annualized return.",
    "unstable_root": "Annualized return is unavailable because the result is numerically unstable.",
    "rate_out_of_range": "Annualized return is outside the supported calculation range.",
    "calculation_limit": "Annualized return is unavailable within the calculation limits.",
    "residual_too_large": "Annualized return is unavailable because the numerical check did not pass.",
    "invalid_cashflow": "Annualized return is unavailable because a cash flow is invalid.",
}


@dataclass(frozen=True)
class DisplayReturn:
    percent: Decimal | None
    annualized: bool
    days_held: int | None
    status: str = "available"
    reason: str = ""
    explanation: str = ""


def display_return(flows: list[tuple[str, Decimal]], on: str, annual_rate: Decimal | XirrResult | None,
                   valued: bool = True) -> DisplayReturn:
    """Flows include purchases, sales, income and terminal value, all in the profile currency.

    Plain return divides net gain by all money invested, so partial sales and income count
    without treating the cost of the remaining units as the original investment.
    Annualized uncertainty comes from the solver; the plain return does not depend on XIRR.
    """
    purchases = [(day, -amount) for day, amount in flows if amount < ZERO]
    if not purchases:
        return DisplayReturn(None, False, None, "unavailable", "insufficient_cashflows",
                             "Not enough dated cash flows to calculate a return.")
    days = (parse_date(on) - parse_date(min(day for day, _ in purchases))).days
    annualized = days >= 365
    invested = sum((amount for _, amount in purchases), ZERO)
    if not valued:
        return DisplayReturn(None, annualized, days, "unavailable", "missing_valuation",
                             "Add missing prices or exchange rates to calculate a return.")
    if not annualized:
        return DisplayReturn(sum((amount for _, amount in flows), ZERO) / invested * 100, False, days)
    result = annual_rate if isinstance(annual_rate, XirrResult) else XirrResult(
        XirrStatus.CONVERGED if annual_rate is not None else XirrStatus.UNAVAILABLE, rate=annual_rate,
        reason="" if annual_rate is not None else "insufficient_cashflows")
    if result.status == XirrStatus.CONVERGED and result.rate is not None:
        return DisplayReturn(result.rate * 100, True, days)
    status = "ambiguous" if result.status == XirrStatus.AMBIGUOUS else "unavailable"
    return DisplayReturn(None, True, days, status, result.reason,
                         _EXPLANATIONS.get(result.reason, "Annualized return is unavailable."))
