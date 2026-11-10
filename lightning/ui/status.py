"""Status sentences (guideline 3.33, A05): the page's answer in words, under its title.

One function per page, from figures the page's services already worked out; nothing here computes money. Each returns
{"text": an English pattern, "values": its numbers}, so the template translates it with `tr` (Arabic lives in i18n).
A sentence states a figure or a plain fact. Never praise, a slogan, or what the tab is for; with nothing to go on it
says what is missing.
"""
from __future__ import annotations

from decimal import Decimal

from lightning.core.money import ZERO, fmt


def sentence(text: str, **values: object) -> dict:
    return {"text": text, "values": values}


def _when(period_key: str, current: bool) -> str:
    """How the sentence names the period: "this month", "in that month", "this year", ..."""
    if period_key == "month":
        return "this month" if current else "that month"
    return {"ytd": "this year", "all": "since your first record"}.get(period_key, "in these dates")


def overview(inflows: Decimal, outflows: Decimal, net: Decimal, savings_rate: Decimal | None, thin: bool,
             period_key: str, current: bool, has_accounts: bool) -> dict:
    """Where do I stand? Told through what was kept of what came in."""
    if not has_accounts:
        return sentence("Add an account to see where you stand.")
    when = _when(period_key, current)
    if inflows <= ZERO:
        if outflows > ZERO:
            return sentence("{amt} went out " + when + " and nothing came in.", amt=fmt(outflows, 0))
        return sentence("Nothing came in or went out " + when + ".")
    if thin or net < ZERO:
        return sentence("{amt} more went out than came in " + when + ".", amt=fmt(-net, 0))
    return sentence("You kept {n}% of what came in " + when + ".", n=f"{savings_rate:.0f}")


def change(value: Decimal | None, period_key: str, current: bool) -> dict | None:
    """The Lead's comparison on Overview: how much net worth moved in the period."""
    if value is None:
        return None
    when = {"month": "this month" if current else "in that month", "ytd": "this year",
            "all": "since your first record"}.get(period_key, "in these dates")
    return {"figure": fmt(value, 0, signed=True), "tone": "good" if value >= ZERO else "bad", "text": when}


def budget(e, has_plan: bool, period_key: str, spent: Decimal, planned: Decimal) -> dict:
    """How much can I still spend? Told against the plan's pace (``e`` is the forecaster's EverydayBudget)."""
    if not has_plan:
        return sentence("Set a plan to see what is left to spend.")
    if period_key != "month" or e is None:
        if spent > planned:
            return sentence("You spent {amt} more than planned in these months.", amt=fmt(spent - planned, 0))
        return sentence("You spent {amt} of the {x} planned.", amt=fmt(spent, 0), x=fmt(planned, 0))
    if e.left < ZERO:
        return sentence("You are {amt} over the plan this month." if e.current else "You went {amt} over the plan that month.",
                        amt=fmt(-e.left, 0))
    if e.current and e.day:
        gap = e.pace_gap
        if gap <= ZERO:
            return sentence("You are {amt} under your plan's pace.", amt=fmt(-gap, 0))
        return sentence("You are {amt} over your plan's pace.", amt=fmt(gap, 0))
    if e.current:
        return sentence("{amt} is left in the plan this month.", amt=fmt(e.left, 0))
    return sentence("You spent {amt} of the {x} planned.", amt=fmt(e.spent, 0), x=fmt(e.planned, 0))


def cash_plan(safe: Decimal, until: str | None, has_income: bool) -> dict:
    """How much is safe to spend before payday?"""
    if not has_income:
        return sentence("Add your salary to see what is safe to spend.")
    if safe < ZERO:
        return sentence("Promised payments are {amt} more than your free cash.", amt=fmt(-safe, 0))
    if until:
        return sentence("You can spend {amt} before payday and stay on plan.", amt=fmt(safe, 0))
    return sentence("You can spend {amt} in the next 3 months and stay on plan.", amt=fmt(safe, 0))


def accounts(count: int, held: Decimal) -> dict:
    """Where is my money?"""
    if not count:
        return sentence("Add an account to see where your money is.")
    if held > ZERO:
        return sentence("{n} accounts. {amt} of it is held for others.", n=count, amt=fmt(held, 0))
    return sentence("{n} accounts, and all of it is yours.", n=count)


def health(within: int, judged: int, outside: list[str]) -> dict:
    """How do my figures compare with my limits?"""
    if not judged:
        return sentence("Add your income and spending to compare them with your limits.")
    if not outside:
        return sentence("All {n} figures are within your limits.", n=judged)
    if len(outside) == 1:
        return sentence("One thing needs you: {name}. Everything else is within your limits.", name=outside[0])
    return sentence("{n} of {m} figures are within your limits.", n=within, m=judged)


def investments(result: Decimal | None, has_holdings: bool, period_key: str, current: bool) -> dict:
    """What do I hold, and how is it doing?"""
    if not has_holdings:
        return sentence("Record a holding to see how your investments are doing.")
    when = _when(period_key, current)
    if result is None:
        return sentence("A price is missing, so the result " + when + " is unavailable.")
    if result == ZERO:
        return sentence("Your holdings' value did not move " + when + ".")
    if result > ZERO:
        return sentence("Your holdings grew {amt} " + when + ".", amt=fmt(result, 0))
    return sentence("Your holdings lost {amt} " + when + ".", amt=fmt(-result, 0))


def spending(total: Decimal, prior: Decimal | None, prior_label: str, period_key: str, current: bool) -> dict:
    """Where did my money go? Told as money out against the period before (3S4)."""
    when = _when(period_key, current)
    if not total:
        return sentence("No money went out " + when + ".")
    if prior:
        gap = total - prior
        if abs(gap) >= 1:
            return sentence("You spent {amt} " + when + ", {gap} " + ("more" if gap > 0 else "less") + " than {label}.",
                            amt=fmt(total, 0), gap=fmt(abs(gap), 0), label=prior_label)
    return sentence("You spent {amt} " + when + ".", amt=fmt(total, 0))


def count(n: int, one: str, many: str, none: str) -> dict:
    """A page that lists things states how many (A05: a plain fact, never what the tab is for)."""
    if not n:
        return sentence(none)
    return sentence(one) if n == 1 else sentence(many, n=n)
