"""What a loan costs, from its optional rate (IV-3H7, owner 2026-11-08). Pure functions, no database.

FLAT: interest on the amount borrowed for the whole term (principal × rate × years), as Egyptian banks quote many
personal and car loans. REDUCING: interest on the balance still owed each month, the usual amortised loan, whose
monthly payment is principal × i / (1 − (1 + i)^−n) with i the monthly rate. Payments stay spending; nothing here
posts or changes a figure anywhere else.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from lightning.core.money import ZERO

FLAT, REDUCING = "FLAT", "REDUCING"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class LoanCost:
    principal: Decimal   # the amount borrowed (given, or worked back from the instalment)
    interest: Decimal    # total interest over the term
    cost: Decimal        # principal + interest: what the loan costs in all
    instalment: Decimal  # the monthly payment the rate implies


def loan_cost(principal: Decimal | None, rate: Decimal, kind: str, months: int,
              instalment: Decimal | None = None) -> LoanCost | None:
    """Total interest and total cost over ``months`` at an annual ``rate`` (percent). Without the amount borrowed
    it is worked back from the monthly ``instalment``. None when neither is known or the term is empty."""
    if months < 1 or rate < ZERO or kind not in (FLAT, REDUCING) or (principal is None and not instalment):
        return None
    yearly, n = Decimal(rate) / 100, Decimal(months)
    if kind == FLAT:
        if principal is None:
            principal = instalment * n / (1 + yearly * n / 12)
        interest = principal * yearly * n / 12
        payment = (principal + interest) / n
    else:
        i = yearly / 12
        if i == ZERO:
            principal = principal if principal is not None else instalment * n
            payment, interest = principal / n, ZERO
        else:
            factor = 1 - (1 + i) ** -months
            if principal is None:
                principal = instalment * factor / i
            payment = principal * i / factor
            interest = payment * n - principal
    principal, interest = _cents(principal), _cents(interest)
    return LoanCost(principal, interest, principal + interest, _cents(payment))


def _cents(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
