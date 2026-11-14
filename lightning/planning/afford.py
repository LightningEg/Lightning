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


def after_payday(forecaster, amount: Decimal, on, account_id: int, day, end) -> Affordability | None:
    """BV-7AW (r37 W7): a purchase dated after the next payday is outside Safe to spend's window, so it is answered by
    the plan's Lowest point ahead with the purchase paid that day (the same measure as Compare scenarios). None when an
    exchange rate is missing."""
    import calendar
    from .scenarios import compare_scenario
    result = compare_scenario(forecaster, day, end, purchase=str(amount), purchase_date=on.isoformat(),
                              account_id=str(account_id))
    low = result.scenario_plan_low
    if low is None:
        return None
    month = calendar.month_name[int(low[0][5:7])]
    if low[1] >= ZERO:
        return Affordability(amount, "yes", low[1], ZERO,
                             f"Yes. Your lowest point ahead would be {low[1]:,.0f} in {month}.")
    return Affordability(amount, "no", low[1], -low[1], f"No. You would be {-low[1]:,.0f} short in {month}.")


def plan_purchase_url(amount: Decimal, on: str, account_id: int | None) -> str:
    """BV-7AW (r37 L3): "Plan this purchase" opens the one-off item form, prefilled; nothing is saved until you save it."""
    from urllib.parse import urlencode
    values = {"kind": "BILL", "frequency": "ONCE", "name": "Purchase", "amount": f"{amount:f}", "start_date": on,
              "back": "/plan"}
    if account_id:
        values["account_id"] = str(account_id)
    return "/plan/items/new?" + urlencode(values)


@dataclass(frozen=True)
class AccountAnswer:
    """One account on one date: scheduled-only, never a guess about spending in between (NF-3AZ6)."""
    account: str
    on: str
    balance_on: Decimal | None   # day-end balance of the account on that date, from posted cash and dated schedule
    after: Decimal | None        # the same, with the purchase paid that day
    lowest_after: Decimal | None  # lowest day-end balance from that date to the end of the window, with the purchase
    short_on: str | None          # first day the account would go below zero with the purchase
    enough: bool | None


def account_check(series, account_id: int, on: str, amount: Decimal, name: str) -> AccountAnswer:
    """``series`` is DatedCashForecast.account_series. The balance on a date is the last day-end point on or before it;
    an account with no point has nothing recorded in it, so its balance is unknown rather than zero."""
    points = [(day, dict(balances)) for day, balances in series]
    before = [balances.get(account_id) for day, balances in points if day <= on and account_id in balances]
    balance_on = before[-1] if before else None
    if balance_on is None:
        return AccountAnswer(name, on, None, None, None, None, None)
    later = [(day, balances[account_id] - amount) for day, balances in points if day >= on and account_id in balances]
    lowest = min([balance_on - amount] + [value for _, value in later])
    short_on = next((day for day, value in [(on, balance_on - amount)] + later if value < ZERO), None)
    return AccountAnswer(name, on, balance_on, balance_on - amount, lowest, short_on, short_on is None)
