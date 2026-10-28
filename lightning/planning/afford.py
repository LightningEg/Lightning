"""Can I afford this? One answer from the Cash planning figures, no new formula.

Safe to spend already holds every promise before the next income (bills, budget, goals). A purchase
that fits inside it is a yes; one that fits only inside free cash eats the plan; anything past free cash
is a no. PC roadmap P4.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal(0)


@dataclass(frozen=True)
class Affordability:
    amount: Decimal
    verdict: str          # "yes" | "plan" | "no"
    left: Decimal         # safe to spend after the purchase (negative when it does not fit)
    short: Decimal        # how much is missing from free cash; 0 unless verdict is "no"
    headline: str


def can_afford(amount: Decimal, safe_to_spend: Decimal, free_cash: Decimal, until: str | None) -> Affordability:
    if amount <= ZERO:
        raise ValueError("Type an amount above zero.")
    left = safe_to_spend - amount
    when = f" until {until}" if until else ""
    if left >= ZERO:
        return Affordability(amount, "yes", left, ZERO, f"Yes. You keep {left:,.0f} safe to spend{when}.")
    if free_cash - amount >= ZERO:
        return Affordability(amount, "plan", left, ZERO,
                             f"Only by cutting your plan: it takes {-left:,.0f} from budget, bills or goals{when}.")
    return Affordability(amount, "no", left, amount - free_cash,
                         f"No. You are {amount - free_cash:,.0f} short of free cash.")
