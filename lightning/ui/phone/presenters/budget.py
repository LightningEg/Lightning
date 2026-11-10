"""The phone's older Budget page (templates/phone/budget.html): the category rows in order of need, the ring and the
one strip, shaped from what the Budget page already worked out (3AY11: the PC route no longer knows the phone)."""
from __future__ import annotations

from decimal import Decimal

from lightning.core.dates import month_of, parse_month, today
from lightning.core.money import ZERO, fmt

from lightning.ui import status as page_status
from lightning.ui.budget_rows import (OVER_NOTE_LABELS, cover_from, month_bills, neighbours, pace_line, plain, plan_ring,
                                      see_all)


def _phone_categories(view, tracked: set[int], category_periods: dict, by_group: dict, period,
                      pace_pct: Decimal | None = None, usual: dict | None = None, month: str = "",
                      bills: dict[int, tuple[Decimal, Decimal]] | None = None) -> list[dict]:
    """One row per category that has a limit, in order of need (3AN7): over plan first (largest overspend first), then
    ahead of the month's pace (furthest ahead first), then by what the category usually costs (its three-month
    average, else its limit). The same figures as the group rows below: what was spent, the limit and what is left.

    Pace is for everyday spending only (BV-3AR): a bill, subscription or loan payment is paid on its day, not spread
    over the month, so a category's scheduled payments leave its pace and only the rest of its plan is paced. A
    category that is only bills says Paid for this month or what is still due; one over its limit is still over."""
    usual, bills = usual or {}, bills or {}
    group_of = {category_id: group_id for group_id, ids in by_group.items() for category_id in ids}
    rows, seen = [], set()
    for section in view.sections:
        for line in section.lines:
            cid = line.category_id
            if line.depth <= 1 or cid in seen or cid not in tracked or cid not in category_periods:
                continue
            seen.add(cid)
            figures = category_periods[cid]
            planned, spent, left = figures["current_budget"], figures["spent"], figures["left"]
            if not planned and not spent:
                continue
            share = (spent / planned * 100) if planned > ZERO else Decimal(100 if spent > ZERO else 0)
            scheduled, paid = bills.get(cid, (ZERO, ZERO))
            everyday_plan = max(planned - scheduled, ZERO)
            everyday_spent = max(spent - paid, ZERO)
            paced = (everyday_spent / everyday_plan * 100) if everyday_plan > ZERO else None
            bill_state = ("" if not scheduled or everyday_plan > ZERO else
                          "paid" if paid >= scheduled else "due")
            # BV-12B: the whole plan paid, and paid as it usually is (as last months), is a settled payment, not a pace risk
            usual_cost = usual.get(cid)
            settled = (not bill_state and planned > ZERO and left >= ZERO and spent >= planned * Decimal("0.99")
                       and bool(usual_cost) and abs(spent - usual_cost) <= usual_cost * Decimal("0.05"))
            if settled:
                bill_state = "paid"
            direct = getattr(line, "direct", None)
            own = direct if direct is not None and not getattr(line, "average_months", None) else None
            rows.append({"category_id": cid, "group_id": group_of.get(cid), "name": line.name, "spent": spent,
                         "planned": planned, "over": left < ZERO, "amount": abs(left), "share": share,
                         "width": round(float(min(max(share, ZERO), Decimal(100))), 1),
                         # M5 pace: everyday spending ahead of the month by 10 points or more, not yet over, is at risk
                         "risk": not settled and left >= ZERO and pace_pct is not None and paced is not None and paced >= pace_pct + 10,
                         "paced": paced if paced is not None else share, "bill": bill_state,
                         "due": max(scheduled - paid, ZERO),
                         "pace": round(float(pace_pct), 1) if pace_pct is not None else None, "cover": "",
                         "usual": usual.get(cid) or planned,
                         "rule": (f"{line.income_percent:f}%" if getattr(line, "income_percent", None) is not None
                                  else plain(own)),
                         "payments": f"/budget/category/{cid}/payments?month={month}" if month else "",
                         "see_all": see_all(cid, month) if month else "",
                         "href": f"/transactions?category_id={cid}&date_from={period.start_text}&date_to={period.end_text}"})
    rows.sort(key=lambda r: (0, -r["amount"], r["name"].casefold()) if r["over"]
              else (1, -(r["paced"] - Decimal(str(r["pace"]))), r["name"].casefold()) if r["risk"]
              else (2, -r["usual"], r["name"].casefold()))
    for r in rows:
        r["line"] = pace_line(r)
    return rows




FIRST_ROWS = 4  # Budget's first screen lists what needs a look and the biggest usual spending, up to four rows


def _split_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """The rows shown at once and the ones behind "N more on track": everything that is over or ahead of pace, then the
    biggest usual spending up to four rows; a short list shows whole."""
    if len(rows) <= FIRST_ROWS + 1:
        return rows, []
    needy = sum(1 for r in rows if r["over"] or r["risk"])
    shown = max(needy, FIRST_ROWS)
    return rows[:shown], rows[shown:]


def _strip(undo: bool, over: dict | None, raise_offer: bool, first_limits: bool) -> str:
    """The one strip under the stepper (3AN7): what was just applied (undo), then a decision waiting (the income raise),
    then what is over plan, then the first limits; the next one takes the place when the one before is gone. What is
    over plan still shows in its rows, in rose."""
    return "undo" if undo else "raise" if raise_offer else "over" if over else "first" if first_limits else ""


def _day_one(has_plan: bool, period, month: str, spent: Decimal, planned: Decimal, days: int) -> dict | None:
    """A new month with nothing spent reads as the plan spread over the month, not "0 of" (3AN7)."""
    if not has_plan or period.key != "month" or month != month_of(today()) or spent > ZERO or planned <= ZERO:
        return None
    return page_status.sentence("New month: {amt} over {n} days", amt=fmt(planned, 0), n=days)


def _phone_over(rows: list[dict], month: str, days_left: int, c, everyday) -> dict | None:
    """The phone's over-plan row: what is over, by how much, and the one action that fixes the largest: move room
    to it when another category has room (Move room), else type its limit (its group opens at the field)."""
    over = [r for r in rows if r["over"]]
    if not over:
        return None
    total = sum((r["amount"] for r in over), ZERO)
    title = (page_status.sentence("{name} is over plan", name=over[0]["name"]) if len(over) == 1
             else page_status.sentence("{n} categories are over plan", n=len(over)))
    if days_left > 1:
        line = page_status.sentence("{amt} over · {n} days left", amt=fmt(total, 0), n=days_left)
    elif days_left == 1:
        line = page_status.sentence("{amt} over · 1 day left", amt=fmt(total, 0))
    else:
        line = page_status.sentence("{amt} over", amt=fmt(total, 0))
    largest = over[0]
    move = (cover_from(c, month, {"category_id": largest["category_id"], "over": largest["amount"]}, everyday.room)
            if everyday is not None else None)
    href = move["href"] if move else (f"/budget?month={month}&open_group={largest['group_id'] or 'all'}"
                                      f"#limit-{largest['category_id']}")
    return {"title": title, "line": line, "count": len(over), "href": href, "popup": bool(move)}


def present(request, c, context: dict) -> dict:
    """What the phone's Budget page adds to the page's own figures. Everything read here is in the PC page's context
    already: the month view, the tracked categories and their period figures, Everyday spending and the plan."""
    month, period, everyday = context["month"], context["period"], context["everyday"]
    month_first, month_last = parse_month(month)
    days_left = (month_last - today()).days + 1 if month_first <= today() <= month_last else 0
    month_days = (month_last - month_first).days + 1
    pace_pct = (Decimal(month_days - days_left) / month_days * 100) if period.key == "month" and days_left else None
    cats = _phone_categories(context["view"], context["tracked"], context["category_periods"], context["by_group"], period,
                             pace_pct, context["averages"], month if period.key == "month" else "",
                             month_bills(c, everyday, month))
    if period.key == "month" and everyday is not None:  # M5: a one-tap Cover on each over row that has a donor
        for r in cats:
            if r["over"]:
                move = cover_from(c, month, {"category_id": r["category_id"], "over": r["amount"]}, everyday.room)
                r["cover"] = move["href"] if move else ""
    shown, rest = _split_rows(cats)
    over_row = _phone_over(cats, month, days_left if period.key == "month" else 0, c, everyday)
    has_plan = context["has_plan"]
    # One strip at a time (3AN7): what was just applied, then what is over plan, then an income raise.
    strip = _strip(bool(context["bulk_undo"]), over_row, bool(context["raise_offer"]), period.key == "month" and not has_plan)
    return {"phone_plan": {
        "ring": plan_ring(context["period_budgeted"], context["period_actual"], context["period_left"]) if has_plan else None,
        "cats": cats, "shown": shown, "rest": rest, "strip": strip,
        "day_one": _day_one(has_plan, period, month, context["period_actual"], context["period_budgeted"], month_days),
        "last_month": neighbours(month)[0], "month": month, "over": over_row,
        "edit_href": f"/budget?month={month}&open_group=all#groups-heading",
        "notes": [n for n in context["notes"] if n.get("label") not in OVER_NOTE_LABELS]}}
