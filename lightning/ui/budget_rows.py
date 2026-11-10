"""Budget rows and their sentences that the PC pages and the phone presenters both draw (3AY11): one home, so the
phone layer never imports the PC routes."""
from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from math import pi
from urllib.parse import quote

from lightning.core.money import ZERO, quantize
from lightning.core.dates import month_of, parse_month, today

from . import keynotes, status as page_status


def neighbours(month: str) -> tuple[str, str]:
    first, last = parse_month(month)
    previous = month_of(first - timedelta(days=1))
    try:
        following = month_of(last + timedelta(days=1))
    except OverflowError:
        following = month
    return previous, following


def see_all(category_id: int, month: str) -> str:
    """A category's payments for a month on the Transactions tab: the month stays chosen (never "Custom range") and ‹ goes
    back to this Budget month, which also keeps Budget the chosen tab (3AN7)."""
    back = quote(f"/budget?month={month}", safe="")
    return f"/transactions?category_id={category_id}&month={month}&return_to={back}"


# The key notes the phone's over-plan row and hero already say (keynotes.budget_left).
OVER_NOTE_LABELS = {"Categories over plan", "Over plan this month"}


RING_RADIUS = 40


def plan_ring(budgeted: Decimal, spent: Decimal, left: Decimal) -> dict | None:
    """The phone's ring: how much of the plan is spent, whole percent, and the arc for it (a full turn at 100%).
    None when nothing is planned, so there is no share to draw."""
    if budgeted <= ZERO:
        return None
    pct = max(int((spent / budgeted * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)), 0)
    circumference = 2 * pi * RING_RADIUS
    return {"pct": min(pct, 999), "wide": pct >= 100, "over": quantize(left, 0) < 0, "amount": abs(left),
            "arc": round(circumference * min(pct, 100) / 100, 2), "circumference": round(circumference, 2)}


def plain(amount: Decimal | None) -> str:
    """An amount as a field holds it: "4666" or "4666.50", no thousands comma."""
    return "" if amount is None else format(amount.normalize(), "f") if amount == amount.to_integral_value() else format(amount, "f")


def pace_line(r: dict) -> dict | None:
    """The category sheet's one pace sentence (3AN7): over, ahead of the month's pace, or on it."""
    if r["over"]:
        return page_status.sentence("Over its limit by {amt}", amt=keynotes.fmt(r["amount"]))
    if r.get("bill") == "paid":  # BV-3AR: a bill is paid on its day, not paced
        return page_status.sentence("Paid for this month")
    if r.get("bill") == "due":
        return page_status.sentence("{amt} still due this month", amt=keynotes.fmt(r["due"]))
    if r["pace"] is None:
        return None
    text = "Ahead of pace: {n}% spent, {m}% of the month gone" if r["risk"] else "On pace: {n}% spent, {m}% of the month gone"
    return page_status.sentence(text, n=round(float(r.get("paced", r["share"]))), m=round(r["pace"]))


def month_bills(c, everyday, month: str) -> dict[int, tuple[Decimal, Decimal]]:
    """The month's scheduled bills, subscriptions and loan payments by category: what is scheduled and what of it is
    paid, in the base currency (BV-3AR). Read from the payments Everyday spending already counts."""
    out: dict[int, tuple[Decimal, Decimal]] = {}
    if everyday is None or not everyday.current:
        return out
    day = today()
    for p in everyday.payments:
        if p.due_date[:7] != month:
            continue
        scheduled, paid = out.get(p.item.category_id, (ZERO, ZERO))
        out[p.item.category_id] = (scheduled + c.planning.amount_in_base(p, p.amount, day),
                                   paid + c.planning.amount_in_base(p, p.amount - p.still_owed, day))
    return out


def cover_from(c, month: str, target: dict, room: dict[int, Decimal]) -> dict | None:
    """The category with the most room left (its bills still to pay set aside) that can cover the largest
    overspend; both need a plan of their own, as Move room asks (budget_move.html)."""
    plans = c.budgets.amounts_for(month, loans=False, schedule=c.schedules.view())
    if target["category_id"] not in plans:
        return None
    amount = Decimal(target["over"]).to_integral_value(rounding=ROUND_CEILING)
    best = max(((left, cid) for cid, left in room.items()
                if cid != target["category_id"] and cid in plans and left >= amount), default=None)
    if best is None:
        return None
    return {"name": c.categories.get(best[1]).name, "amount": amount,
            "href": f"/budget/move?month={month}&to={target['category_id']}&from={best[1]}&amount={amount}"}
