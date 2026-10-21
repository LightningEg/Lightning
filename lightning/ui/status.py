"""Status sentences (guideline 3.33, A05): the page's answer in words, under its title.

One function per page, from figures the page's services already worked out; nothing here computes money. Each returns
{"text": an English pattern, "values": its numbers}, so the template translates it with `tr` (Arabic lives in i18n).
A sentence states a figure or a plain fact. Never praise, a slogan, or what the tab is for; with nothing to go on it
says what is missing.
"""
from __future__ import annotations

from decimal import Decimal

from lightning.core.money import ZERO

from .keynotes import fmt


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
            return sentence("{amt} went out " + when + " and nothing came in.", amt=fmt(outflows))
        return sentence("Nothing came in or went out " + when + ".")
    if thin or net < ZERO:
        return sentence("{amt} more went out than came in " + when + ".", amt=fmt(-net))
    return sentence("You kept {n}% of what came in " + when + ".", n=f"{savings_rate:.0f}")


def change(value: Decimal | None, period_key: str, current: bool) -> dict | None:
    """The Lead's comparison on Overview: how much net worth moved in the period."""
    if value is None:
        return None
    when = {"month": "this month" if current else "in that month", "ytd": "this year",
            "all": "since your first record"}.get(period_key, "in these dates")
    return {"figure": fmt(value, signed=True), "tone": "good" if value >= ZERO else "bad", "text": when}


def budget(e, has_plan: bool, period_key: str, spent: Decimal, planned: Decimal) -> dict:
    """How much can I still spend? Told against the plan's pace (``e`` is the forecaster's EverydayBudget)."""
    if not has_plan:
        return sentence("Set a plan to see what is left to spend.")
    if period_key != "month" or e is None:
        if spent > planned:
            return sentence("You spent {amt} more than planned in these months.", amt=fmt(spent - planned))
        return sentence("You spent {amt} of the {x} planned.", amt=fmt(spent), x=fmt(planned))
    if e.left < ZERO:
        return sentence("You are {amt} over the plan this month." if e.current else "You went {amt} over the plan that month.",
                        amt=fmt(-e.left))
    if e.current and e.day:
        gap = e.everyday_spent - e.pace
        if gap <= ZERO:
            return sentence("You are {amt} under your plan's pace.", amt=fmt(-gap))
        return sentence("You are {amt} over your plan's pace.", amt=fmt(gap))
    if e.current:
        return sentence("{amt} is left in the plan this month.", amt=fmt(e.left))
    return sentence("You spent {amt} of the {x} planned.", amt=fmt(e.spent), x=fmt(e.planned))


def cash_plan(safe: Decimal, until: str | None, has_income: bool) -> dict:
    """How much is safe to spend before payday?"""
    if not has_income:
        return sentence("Add your salary to see what is safe to spend.")
    if safe < ZERO:
        return sentence("Promised payments are {amt} more than your free cash.", amt=fmt(-safe))
    if until:
        return sentence("You can spend {amt} before payday and stay on plan.", amt=fmt(safe))
    return sentence("You can spend {amt} in the next 3 months and stay on plan.", amt=fmt(safe))
