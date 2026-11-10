"""The phone's older Overview (templates/phone/dashboard/index.html), which a period link still opens until Money's
net worth sheet takes its parts (3AY10): the Safe to spend hero, the words on the Needs you card, the list without
value updates and the month grid, shaped from the Overview's own figures (3AY11)."""
from __future__ import annotations

from urllib.parse import urlencode

from lightning.core.dates import parse_date, today
from lightning.core.figures import label
from lightning.core.money import ZERO, fmt as _fmt
from lightning.core.refs import DocType
from lightning.planning.bill_state import NEEDS_ACTION, open_bills
from lightning.ui import status as page_status, visuals


def fmt(value, places: int = 0, signed: bool = False) -> str:
    return _fmt(value, places, signed)


# Needs you on the phone says what is inside in a few words (phone overhaul 2026-10-22): "2 bills · 4 to sort out".
_NEEDS_SHORT = {"payments": ("1 bill", "{n} bills"), "activity": ("1 to sort out", "{n} to sort out"),
                "budget": ("1 on the budget", "{n} on the budget"), "cash": ("1 on cash", "{n} on cash"),
                "prices": ("1 price", "{n} prices"), "other": ("1 other", "{n} others"),
                "match": ("1 to match", "{n} to match"), "payment": ("1 payment to check", "{n} payments to check")}


def _needs_parts(groups: list[dict], limit: int = 3) -> list[dict]:
    """The words under Needs you's title, one per kind of thing inside (3AN1). The payments group holds bills but
    also interest to match and payments to check, so it is split by what each item is: a match is "1 to match",
    never "1 bill"."""
    counts: dict[str, int] = {}
    for group in groups:
        if group["key"] != "payments":
            counts[group["key"]] = group["count"]
            continue
        for item in group.get("items") or [{}]:
            label, href = item.get("label", ""), item.get("href", "")
            kind = ("match" if href.startswith("/deposits/") else
                    "payments" if label.startswith(("Bill due", "Loan payment due")) else "payment")
            counts[kind] = counts.get(kind, 0) + 1
    parts = []
    for key, n in counts.items():
        one, many = _NEEDS_SHORT.get(key, _NEEDS_SHORT["other"])
        parts.append(page_status.sentence(one if n == 1 else many, n=n))
    return parts[:limit]


def _safe_hero(f) -> dict:
    """Safe to spend as the phone's hero (phone overhaul 2026-10-22: "can I spend today?"), with its one sentence:
    about how much a day until payday. ``f`` is today's forecast; the figure's home stays Cash planning."""
    value, until = f.safe_to_spend, f.next_income_date
    days = (parse_date(until) - today()).days if until else 0
    if value < 0:
        line = page_status.sentence("{amt} more is promised than your free cash.", amt=fmt(-value))
    elif until and days > 0:
        line = page_status.sentence("On top of your plan until {sa}.", sa=until)  # no per-day figure: Budget owns it (BV-12A)
    else:
        line = page_status.sentence("From free cash, after what is promised over the next 3 months.")
    return {"value": value, "line": line, "until": until or ""}


def _worth_tile(position, lead_change) -> dict:
    """The phone's Net worth tile (C06.1: with Left in plan, the only two on Overview)."""
    owes = position.what_you_owe > 0
    return {"key": "networth", "surface": "hold", "label": label("net_worth" if owes else "what_you_own"),
            "value": position.net_worth if owes else position.what_you_own, "kind": "money",
            "badge": {"tone": "flat", "text": "Today"},
            "sub": f"{lead_change['figure']} {lead_change['text']}" if lead_change else "",
            "href": "/accounts"}


def _phone_overview(forecast, groups, c, attention=()) -> dict:
    """What the phone's Overview adds to the PC's figures: the Safe to spend hero and the words on the Needs you card
    (3AN4: the next bill due within three days, named, so the bill's pay sheet is one tap from Overview)."""
    soon = _due_soon(c, attention)
    return {"safe": _safe_hero(forecast), "needs": _needs_parts(groups), "soon": soon,
            "needs_count": len(attention) + (soon["extra"] if soon else 0)}


DUE_SOON_DAYS = 3  # Needs you names a bill due today, late, or within three days (guideline C04.4)


def _due_line(name: str, amount: str, days: int, late: int) -> dict:
    """"Landlord 12,000 in 2 days": the bill Needs you names, as a translatable sentence."""
    if late:
        return page_status.sentence("{name} {amt}, 1 day late" if late == 1 else "{name} {amt}, {n} days late",
                                    name=name, amt=amount, n=late)
    if days == 0:
        return page_status.sentence("{name} {amt} today", name=name, amt=amount)
    if days == 1:
        return page_status.sentence("{name} {amt} tomorrow", name=name, amt=amount)
    return page_status.sentence("{name} {amt} in {n} days", name=name, amt=amount, n=days)


def _due_soon(c, attention=()) -> dict | None:
    """Phone Needs you (C04.4, 3AN4): the bills, subscriptions and loan payments that are late or due within three
    days, earliest first, each with its pay sheet. ``next`` is the one the card names ("Landlord 12,000 in 2 days");
    ``extra`` counts the ones the review inbox does not already list (it lists what is due today or late)."""
    day = today()
    due = sorted((r.payment for r in open_bills(c.planning, day, DUE_SOON_DAYS) if r.state in NEEDS_ACTION),
                 key=lambda p: p.due_date)  # one bill state (3AY5): late, stale or due within three days
    if not due:
        return None
    known = {str(item.get("href", "")).split("&")[0] for item in attention}
    rows = []
    for p in due:
        late = p.days_late(day)
        pay = f"/plan/items/{p.item.id}/pay?due={p.due_date}&back=%2F"
        amount = c.planning.amount_in_base(p, p.still_owed, day)
        days = 0 if late else (parse_date(p.due_date) - day).days
        rows.append({"name": p.item.name, "amount": amount, "late": late, "days": days, "pay": pay,
                     "listed": pay.split("&")[0] in known, "line": _due_line(p.item.name, fmt(amount), days, late)})
    return {"count": len(rows), "total": sum((r["amount"] for r in rows), ZERO), "late": any(r["late"] for r in rows),
            "next": rows[0], "rows": rows, "extra": sum(1 for r in rows if not r["listed"])}


def _recent_rows(c, shown: int = 10) -> list:
    """The latest rows without value updates: a month-end revaluation is not money moving."""
    start, end = "1900-01-01", "9999-12-31"
    rows, total, _ = c.reporting.register_page(None, start, end, 1, shown)
    if not c.reporting.register_value_updates(None, start, end):
        return rows
    rows = [row for row in rows if row.type != DocType.VAL]
    page = 1
    while len(rows) < shown and page * shown < total:
        page += 1
        more, _, _ = c.reporting.register_page(None, start, end, page, shown)
        rows.extend(row for row in more if row.type != DocType.VAL)
    return rows[:shown]


def present(request, c, context: dict) -> dict:
    phone = (_phone_overview(c.forecaster.forecast(today()), context["attention_groups"], c, context["attention"])
             if context["position_is_today"] else None)
    return {"phone": phone, "recent_rows": _recent_rows(c),
            "worth_tile": _worth_tile(context["pos"], context["lead_change"]) if phone and phone.get("safe") else None,
            "month_calendar": visuals.month_calendar(c, today()),
            # the trend and the money-in flow stay in closed folds and load when opened (backend roadmap B1)
            "lazy_folds": True, "fold_query": urlencode(request.query_params)}
