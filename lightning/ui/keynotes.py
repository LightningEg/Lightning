"""Key notes: each page's answer in up to three small cards: a label, one big figure, one line.

Notes only phrase figures that services already computed (the position, cash flow, budget,
forecast, investment report); they never compute a figure of their own beyond comparing two of
them. Names follow lightning/core/figures.py.
"""
from __future__ import annotations

from decimal import Decimal

from lightning.core.figures import FIGURES
from lightning.core.money import ZERO, fmt as _fmt


def fmt(value, places: int = 0, signed: bool = False) -> str:
    """Reporting text rounds to the nearest unit (stored values keep their decimals)."""
    return _fmt(value, places, signed)


# Icon by what the note is about (App guideline · Key notes); the first match wins.
_ICONS = [("over plan", "alert"), ("run short", "alert"), ("safe to spend", "wallet"), ("lowest point", "chart"),
          ("emergency fund", "shield"), ("loan", "calendar"), ("paid off", "calendar"), ("still to pay", "calendar"),
          ("hold money for", "people"), ("hold nothing", "people"), ("valued at cost", "tag"), ("selling", "tag"),
          ("grew", "up"), ("earned", "up"), ("kept", "up"), ("more than", "up"), ("above", "up"),
          ("fell", "down"), ("lost", "down"), ("less than", "down"), ("down", "down"),
          ("%", "pie"), ("nothing needs you", "check")]
_DEFAULT_ICON = {"good": "check", "info": "bulb", "attention": "alert"}


def note_icon(tone: str, title: str) -> str:
    lower = title.lower()
    return next((icon for word, icon in _ICONS if word in lower), _DEFAULT_ICON.get(tone, "bulb"))


def note(tone: str, title: str, text: str, href: str = "", action: str = "", popup: bool = False,
         icon: str = "", label: str = "", figure: str = "") -> dict:
    """``title`` is the whole sentence (read out to screen readers). A card shows ``label`` small,
    ``figure`` big and ``text`` under it; a note without a figure shows its title instead."""
    return {"tone": tone, "title": title, "text": text, "href": href, "action": action, "popup": popup,
            "icon": icon or note_icon(tone, title), "label": label, "figure": figure}


def _signed(value: Decimal) -> str:
    return ("+" if value > 0 else "−" if value < 0 else "") + fmt(abs(value))


def change_in_what_you_own(change: Decimal | None, period_label: str, href: str) -> dict | None:
    if change is None:
        return None
    if change >= 0:
        return note("good", f"What you own grew {fmt(change)}", f"{period_label} · saving, prices and new balances.",
                    href, "See how", label="What you own grew", figure=_signed(change))
    return note("attention", f"What you own fell {fmt(-change)}", f"{period_label} · check spending and prices.",
                href, "See how", label="What you own fell", figure=_signed(change))


def kept(flow, period_label: str, href: str) -> dict | None:
    if not flow.inflows and not flow.outflows:
        return None
    if flow.net >= 0 and flow.savings_rate is not None:
        return note("good", f"You kept {flow.savings_rate:.0f}% of money in",
                    f"{fmt(flow.net)} of {fmt(flow.inflows)} that came in.", href, "See where it went",
                    label=f"Saved · {period_label}", figure=f"{flow.savings_rate:.1f}%")
    return note("attention", f"You spent {fmt(-flow.net)} more than came in",
                f"{fmt(flow.outflows)} out against {fmt(flow.inflows)} in.", href, "See where it went",
                label=f"Spent more than came in · {period_label}", figure=fmt(-flow.net))


def needs_you(attention: list[dict], safe_to_spend: Decimal | None, next_income: str | None) -> dict:
    if attention:
        first = attention[0]
        more = f" and {len(attention) - 1} more" if len(attention) > 1 else ""
        return note("attention", first["label"] + more, first["detail"], first["href"], first.get("action") or "Review",
                    popup=bool(first.get("popup")))
    if safe_to_spend is not None:
        until = f" until {next_income}" if next_income else ""
        return note("info", f"{fmt(safe_to_spend)} safe to spend{until}",
                    "Free cash less what is due before your next income.", "/plan", "See the plan",
                    label="Safe to spend" + until, figure=fmt(safe_to_spend))
    return note("info", "Nothing needs you today", "No bills are due and nothing is waiting for a decision.")


def top_category(groups: list, total: Decimal, href: str) -> dict | None:
    if not groups or not total:
        return None
    top = max(groups, key=lambda g: g["value"])
    share = top["value"] / total * 100
    return note("info", f"{top['label']} took {share:.0f}% of spending", f"{fmt(top['value'])} of {fmt(total)}.",
                top.get("href") or href, "See transactions", label=f"{top['label']} · share of spending",
                figure=f"{share:.0f}%")


def compared(spent: Decimal, prior: Decimal | None, prior_label: str) -> dict | None:
    if prior is None:
        return None
    if not prior:
        return note("info", "No earlier spending to compare", f"Nothing was spent in {prior_label}.")
    diff = spent - prior
    if diff > 0:
        return note("attention", f"{fmt(diff)} more than {prior_label}", f"{fmt(spent)} against {fmt(prior)}.",
                    label=f"More than {prior_label}", figure=_signed(diff))
    if diff < 0:
        return note("good", f"{fmt(-diff)} less than {prior_label}", f"{fmt(spent)} against {fmt(prior)}.",
                    label=f"Less than {prior_label}", figure=_signed(diff))
    return note("info", f"The same as {prior_label}", f"{fmt(spent)} both times.")


def budget_left(left: Decimal, days_left: int, over: list[str], href: str) -> list[dict]:
    """Only what the summary cards don't say: which categories went over plan."""
    if over:
        names = ", ".join(over[:2]) + (f" and {len(over) - 2} more" if len(over) > 2 else "")
        return [note("attention", f"{names} over plan", names + ".", href, "See categories",
                     label="Categories over plan", figure=str(len(over)))]
    if left < 0:
        return [note("attention", f"{fmt(-left)} over plan this month", "Cut back or raise a category's plan.",
                     label="Over plan this month", figure=fmt(-left))]
    return []


def _percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('1'))}%"


def plan_check(check) -> list[dict]:
    """A plan that leaves less than the savings target, or less than dated goals need (health.PlanCheck)."""
    if not check.over_by or check.planned_savings_rate is None:
        return []
    if check.short_for == "goals":
        return [note("attention", f"This plan leaves {fmt(check.plan_saves)}; {check.needs_label} {fmt(check.needs)}",
                     f"Plan {fmt(check.over_by)} less, or give a goal a later date." if check.goals else
                     f"Plan {fmt(check.over_by)} less to rebuild it within two years.", "/plan/reserves", "See reserves",
                     label="Short for your goals" if check.goals else "Short for your emergency fund",
                     figure=fmt(check.over_by))]
    return [note("attention", f"This plan saves {_percent(check.planned_savings_rate)}; your target is "
                 f"{_percent(check.target_percent)}",
                 f"Plan {fmt(check.over_by)} less to keep {fmt(check.to_save)} a month.",
                 "/settings?section=financial-health", "Savings target",
                 label="Below your savings target", figure=_percent(check.planned_savings_rate))]


def per_day(left: Decimal, days_left: int) -> str:
    """Under Left in plan: what it means for the rest of the month."""
    if left < 0:
        return "Spending passed the plan"
    if days_left <= 0:
        return "The month is over"
    if days_left == 1:
        return "Today is the last day of the month"
    return f"About {fmt(left / days_left)} a day for {days_left} days"


def best_class(class_rows: list[dict]) -> dict | None:
    gains = [r for r in class_rows if r["result"]]
    if not gains:
        return None
    best = max(gains, key=lambda r: r["result"])
    if best["result"] <= 0:
        worst = min(gains, key=lambda r: r["result"])
        return note("attention", f"{worst['label']} lost {fmt(-worst['result'])}", "Its prices fell in this period.",
                    label=f"{worst['label']} lost", figure=_signed(worst["result"]))
    return note("good", f"{best['label']} earned the most: {_signed(best['result'])}", "Prices, sales and dividends in this period.",
                label=f"Best class · {best['label']}", figure=_signed(best["result"]))


def at_cost(items: list[dict]) -> dict | None:
    if not items:
        return None
    names = ", ".join(i["asset"] for i in items[:2]) + (f" and {len(items) - 2} more" if len(items) > 2 else "")
    return note("info", f"{len(items)} holding(s) valued at cost", f"{names}: no price yet, so no gain is shown.",
                "/investments/prices", "Update prices", label="Holdings valued at cost", figure=str(len(items)))


def emergency(fund) -> dict | None:
    """How long the emergency fund lasts, in months of the average Settings › Budget names."""
    months = fund.months
    if months is None:
        how = ("Set your income categories" if fund.basis == "income" else "Record a month of spending")
        return note("info", "Emergency fund not measured yet", f"{how} so months covered can be worked out.",
                    "/settings?section=budget", "Open settings")
    tone = "good" if months >= 6 else "attention" if months < 1 else "info"
    of = FIGURES[fund.figure].label
    return note(tone, f"Emergency fund covers {months:.1f} months", f"Of {of[0].lower() + of[1:]}. The aim is six.",
                label="Emergency fund covers", figure=f"{months:.1f} months")


def loans_summary(loans: list[dict]) -> dict | None:
    if not loans:
        return None
    left = sum((entry["progress"]["still_to_pay"] for entry in loans), ZERO)
    ends = max((entry["progress"]["last_date"] or "" for entry in loans), default="")
    due = sum(len(entry["progress"]["due"]) for entry in loans)
    if due:
        return note("attention", f"{due} loan payment{'s' if due > 1 else ''} due now",
                    f"{fmt(left)} still to pay. The last payment is on {ends}.",
                    label="Loan payments due now", figure=str(due))
    paid = sum(entry["progress"]["paid"] for entry in loans)
    total = sum(entry["progress"]["total"] for entry in loans)
    return note("good" if paid else "info", f"Paid off on {ends}" if ends else f"{fmt(left)} still to pay",
                f"{paid} of {total} payments made.", label="Paid off on" if ends else "Still to pay",
                figure=ends or fmt(left))


def held_for_others(owners: list[dict], total: Decimal | None) -> dict | None:
    if not owners:
        return note("info", "You hold nothing for anyone", "Money you keep for family or friends shows here, apart from what you own.")
    names = sorted({row["owner"] for row in owners})
    who = ", ".join(names[:2]) + (f" and {len(names) - 2} more" if len(names) > 2 else "")
    amount = f"{fmt(total)} in all. " if total else ""
    return note("info", f"You hold money for {who}", "It stays in your accounts but is not counted as yours.",
                label=f"Held for {who}", figure=fmt(total) if total else "")


def low_confidence_note(estimates: list[dict]) -> str:
    """The words behind the small "!" beside a plan that counts a low-confidence estimate."""
    if not estimates:
        return ""
    parts = [f"{_fmt(e['estimate'], 0)} for {e['name']}" for e in estimates]
    months = {e["observed"] for e in estimates}
    basis = "one month of spending" if months == {1} else "too few months of spending"
    return (f"Includes {', '.join(parts)}: an estimate from {basis}, so it is low confidence. "
            "Set a limit on Budget to replace it.")
