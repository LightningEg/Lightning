"""Cash planning: Plan · Upcoming · Recurring · Loans · Reserves."""
from __future__ import annotations

import calendar
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from lightning.categories.domain import Direction, Movement
from lightning.core.dates import fmt_date, month_of, parse_date, parse_month, today
from lightning.core.errors import LightningError, ValidationError
from lightning.core.figures import label
from lightning.core.money import ZERO, fmt, to_decimal
from lightning.core.plural import counted
from lightning.planning.domain import (FREQUENCY_LABELS, KIND_LABELS, RECURRING_KINDS, WEEKEND_MOVE_LABELS, Frequency,
                                       PaymentStatus, PlanKind, WeekendMove, per_year)
from lightning.planning.bill_state import CATCH_UP_FROM, late_payments
from lightning.planning.schedule import describe
from lightning.planning.service import LOAN_CATEGORY

from .. import charts, keynotes, kpis, visuals, status as page_status
from ..web import container, redirect, render, settled_save
from . import reserves as reserve_routes

router = APIRouter(prefix="/plan")

FIELDS = ("kind", "name", "amount", "frequency", "interval_count", "start_date", "end_date", "payment_count",
          "account_id", "category_id", "counterparty", "principal", "notes", "weekend_move",
          "match_window_days", "match_tolerance_pct")
TABS = (("plan", "Plan", "/plan"), ("upcoming", "Upcoming", "/plan/upcoming"), ("recurring", "Recurring", "/plan/recurring"),
        ("loans", "Loans", "/plan/loans"), ("reserves", "Reserves", "/plan/reserves"))


def _category_options(c, movement: Movement) -> list[dict]:
    by_id = {cat.id: cat for cat in c.categories.tree()}
    options = []
    for cat in by_id.values():
        if not cat.active or cat.is_system or cat.depth != 2 or (cat.movement != movement and cat.direction != Direction.BOTH):
            continue
        parent = by_id.get(cat.parent_id)
        options.append({"id": cat.id, "label": f"{parent.name} › {cat.name}" if parent else cat.name})
    return sorted(options, key=lambda o: o["label"].casefold())


def _labels(c) -> dict:
    accounts = {a.id: a.name for a in c.accounts.list()}
    categories = {cat.id: cat.name for cat in c.categories.tree()}
    reserves = {row["planned_item_id"]: row for row in c.reserves.list_active() if row.get("planned_item_id")}
    return {"accounts": accounts, "categories": categories, "bill_reserves": reserves}


def _row(c, item, labels, as_of, linked):
    horizon = as_of + timedelta(days=400)
    payments = c.planning.payments(item, item.end_date or fmt_date(horizon), as_of)
    upcoming = next((p for p in payments if p.outstanding), None)
    due = [p for p in payments if p.status == PaymentStatus.DUE]
    last = next((p for p in reversed(payments) if p.status == PaymentStatus.PAID), None)
    review_next = bool(upcoming and upcoming.status == PaymentStatus.UPCOMING and any(
        candidate["id"] not in linked for candidate in c.planning.plausible_candidates(upcoming, as_of)))
    per_year = c.planning.amount_in_base(item, _per_year(item), as_of)
    recent = fmt_date(as_of - timedelta(days=62))
    skipped = [p for p in payments if p.status == PaymentStatus.SKIPPED and p.due_date >= recent]
    reserve_links = c.reserves.links_for_transaction(last.transaction_id) if last and last.transaction_id else []
    return {"item": item, "schedule": describe(item), "next": upcoming, "due": due, "last_paid": last, "skipped": skipped,
            "account": labels["accounts"].get(item.account_id), "category": labels["categories"].get(item.category_id),
            "per_year": per_year, "reserve_links": reserve_links, "review_next": review_next,
            "bill_reserve": labels["bill_reserves"].get(item.id)}


_per_year = per_year  # one calculation, in lightning.planning.domain


def _form_values(form) -> dict:
    return {k: str(form.get(k, "")).strip() for k in FIELDS}


def _save_values(c, values: dict) -> dict:
    """Form fields → service values; a typed "paid to" name becomes a saved Counterparty."""
    name = values.get("counterparty", "")
    party = None
    if name:
        found = c.counterparties.resolve(name)
        party = found["id"] if found else c.counterparties.create(name)
    return {k: v for k, v in values.items() if k != "counterparty"} | {"counterparty_id": party}


def _back(form, default: str) -> str:
    back = str(form.get("back", ""))
    return back if back.startswith("/plan") else default


def _paying_accounts(c):
    """Accounts a bill is paid from or income is paid into: banks and wallets first, then brokerage."""
    order = {"BANK": 0, "CASH": 1, "BROKERAGE": 2}
    return sorted((a for a in c.accounts.list(active_only=True) if a.account_type.value in order),
                  key=lambda a: order[a.account_type.value])


# ------------------------------------------------------------------- tabs
def _circle_rows(c, day, window_end) -> list[dict]:
    """CP-3 (3H2): gam'eya instalments and payouts in the next 30 days beside the bills, overdue ones first, each
    opening its circle to record it. Dates and amounts are the circle's own (GameyaService), as the forecast uses."""
    names = {a.id: a.name for a in c.accounts.list(active_only=False)}
    rows = []
    for circle, _ in c.gameya.circles():
        progress = c.gameya.progress(circle.id, day)
        if progress.due_count:
            rows.append({"name": names.get(circle.id, ""), "date": progress.next_date, "late": True,
                         "what": "1 instalment due" if progress.due_count == 1 else f"{progress.due_count} instalments due",
                         "amount": -progress.due_amount, "href": f"/gameya/{circle.id}"})
    for event in c.gameya.future_events(day, window_end):
        if event.kind in ("INSTALLMENT", "PAYOUT"):
            rows.append({"name": names.get(event.deposit_account_id, ""), "date": event.date, "late": False,
                         "what": "Instalment" if event.kind == "INSTALLMENT" else "Your payout",
                         "amount": event.amount, "href": f"/gameya/{event.deposit_account_id}"})
    return sorted(rows, key=lambda r: (not r["late"], r["date"] or ""))


@router.get("")
async def plan_page(request: Request):
    c = container(request)
    day = today()
    forecast = c.forecaster.forecast(day)
    owe = c.planning.what_you_owe(day)
    window_end = day + timedelta(days=30)
    next_payments = [p for p in c.planning.all_payments(window_end, day)
                     if p.status in (PaymentStatus.DUE, PaymentStatus.UPCOMING)]
    # Late payments first, each with its days late (computed here, not in the template).
    next_payments.sort(key=lambda p: (not p.days_late(day), p.due_date, p.item.name.casefold()))
    late_days = {(p.item.id, p.due_date): p.days_late(day) for p in next_payments if p.days_late(day)}
    circle_rows = _circle_rows(c, day, window_end)
    plan = visuals.cash_plan(c, forecast, day)
    # Honest numbers (A01): with no income planned there is nothing to forecast from.
    has_income = bool(c.planning.items((PlanKind.INCOME,)))
    stats = _plan_stats(forecast, plan, day, has_income)
    # KPI cards (guideline 3.32 A08): each figure against something. Free cash against the last month end it
    # was at, payments before payday with the late ones, the lowest point against today.
    past = [(key, value) for key, value in plan["past_free"] if value is not None]
    late = [p for p in next_payments if p.days_late(day) and not p.item.is_income]
    position = c.position.at(day)
    kpi_cards = kpis.cash_plan(forecast, day=day, before=plan["before_income"], late=late,
                               late_total=c.planning.still_owed_in_base(late, day),
                               free_then=past[-1][1] if past else None,
                               then=fmt_date(parse_month(past[-1][0])[1]) if past else "",
                               past_free=[value for _, value in past], position=position,
                               monthly_spending=c.budgets.spending_average(month_of(day)).amount, has_income=has_income)
    # Answer first (guideline 3.33, A09): Safe to spend is the page's Lead with its working beside it; late payments are
    # Needs you rows under it, each with Mark paid.
    lead = next((k for k in kpi_cards if k["key"] == "safe"), None)
    kpi_cards = [k for k in kpi_cards if k["key"] != "safe"]
    needs = [{"label": f"{p.item.name} is late", "detail": f"Due {p.due_date} · {fmt(p.still_owed, 0)} · {p.days_late(day)} days late",
              "href": f"/plan/items/{p.item.id}/pay?due={p.due_date}&back=%2Fplan", "popup": True, "action": "Mark paid"}
             for p in late]
    if len(late) >= CATCH_UP_FROM:
        # IV-12AA5: many late payments are one Catch up, each in turn, not a row and a Mark paid each.
        names = ", ".join(p.item.name for p in late[:2]) + (f" and {len(late) - 2} more" if len(late) > 2 else "")  # not money: counts and keys
        needs = [{"label": f"{len(late)} payments are late", "detail": names, "href": "/plan/catch-up",
                  "action": "Catch up"}]
    status = page_status.cash_plan(forecast.safe_to_spend, forecast.next_income_date, has_income)
    afford, afford_error = None, ""
    raw_afford = request.query_params.get("afford", "").replace(",", "").strip()
    if raw_afford:
        from lightning.planning.afford import can_afford
        try:
            afford = can_afford(Decimal(raw_afford), forecast.safe_to_spend, forecast.free_cash, forecast.next_income_date)
        except (ArithmeticError, ValueError):
            afford_error = "Type an amount above zero."
    afford_account = _afford_account_answer(c, request, afford, day)
    has_accounts = bool(c.accounts.list())
    has_items = bool(c.planning.items())
    empty_profile = (not has_accounts and not has_items
                     and not c.accounts.list(active_only=False) and not c.reserves.list_active())
    return render(request, "planning/plan.html", has_accounts=has_accounts, empty_profile=empty_profile,
              afford_account=afford_account,
                  afford_accounts=[a for a in _paying_accounts(c) if a.currency == c.base_currency],
                  afford_date=str(request.query_params.get("afford_date", "")),
                  afford_account_id=str(request.query_params.get("afford_account", "")), tabs=TABS, plan_tab="plan", forecast=forecast, owe=owe, has_income=has_income,
                  lead=lead, needs=needs, status=status, afford=afford, afford_error=afford_error,
                  afford_amount=raw_afford,
                  gameya_owed=position.gameya_still_to_pay,
                  notes=[], plan=plan, stats=stats, kpi_cards=kpi_cards, forecast_chart=visuals.forecast_trend(forecast),
                  next_payments=next_payments, late_days=late_days, circle_rows=circle_rows,
                  upcoming=[p for p in next_payments if p not in late],  # IV-12Z2: the PC lists late bills in Needs you only
                  as_of=fmt_date(day), window_end=fmt_date(window_end),
                  has_items=has_items, labels=_labels(c), zakat=c.zakat.forecast(day))


def _plan_stats(f, plan, day, has_income: bool = True) -> list[dict]:
    """Four cards: safe to spend, free cash, what is due before the next income, the lowest point ahead."""
    until = f.next_income_date
    low = f.lowest if has_income else None
    short = f.first_short_month if has_income else None
    nxt = plan["before_income"][0] if plan["before_income"] else None
    return [
        {"key": "safe", "surface": "hold", "label": label("safe_to_spend"), "value": f.safe_to_spend, "kind": "money",
         "badge": {"tone": "over" if f.safe_to_spend < 0 else "flat", "text": f"until {until}" if until else "3 months"},
         "sub": (f"On top of your plan until {until}" if f.safe_to_spend > 0 and until
                 else "On top of your plan for the next 3 months" if f.safe_to_spend > 0
                 else "Promised payments are larger than your free cash" if f.safe_to_spend < 0 else "Nothing left to spend safely"),
         "href": "#plan-build"},
        {"key": "free", "surface": "hold", "label": label("free_cash"), "value": f.free_cash, "kind": "money",
         "sub": "", "href": "/"},
        {"key": "before", "surface": "out", "label": label("payments_before_next_income"), "value": plan["before_total"], "kind": "money",
         "badge": {"tone": "flat", "text": f"{counted(len(plan['before_income']), 'payment', 'payments')}"},
         "sub": f"Next: {nxt.item.name} · {nxt.due_date}" if nxt else "Nothing is due before then",
         "href": "#plan-next"},
        {"key": "low", "surface": "over" if low and low.closing < 0 else "hold", "label": "Lowest point ahead", "value": low.closing if low else None, "kind": "money",
         "empty": "—", "badge": {"tone": "over" if low and low.closing < 0 else "flat", "text": low.month if low else "—"},
         "sub": (f"Runs short in {short.month}: the month ends below your reserves" if short
                 else "" if low else "Add your bills and income to see it"),
         "spark": plan["forecast_spark"], "spark_tone": "over" if low and low.closing < 0 else "hold", "href": "#plan-forecast"},
    ]


def _ratio_tile(ratio, as_of: str, sub: str, missing: str, href: str = "", over: bool = False) -> dict:
    """One KPI card per ratio (A08): its percent, the two amounts it divides, and a meter up to 100%."""
    pct = ratio.percent
    return {"key": ratio.key, "surface": "over" if over else "out", "label": label(ratio.key), "value": pct,
            "kind": "rate", "empty": "—", "badge": {"tone": "flat", "text": as_of},
            "sub": sub if pct is not None and ratio.part else missing, "href": href,
            "meter": {"width": float(min(pct, 100)), "tone": "spend"} if pct is not None else None}


def _debt_tiles(h, as_of: str) -> list[dict]:
    """Cash planning › Loans: is my debt under control? Each ratio its own card."""
    owed, worth, cash = h.debt_to_net_worth.part, h.debt_to_net_worth.whole, h.debt_to_cash.whole
    loans, income = h.loan_payments_to_income.part, h.loan_payments_to_income.whole
    return [
        _ratio_tile(h.debt_to_net_worth, as_of, f"{fmt(owed, 0)} owed against {fmt(worth, 0)} net worth",
                    "You owe more than you own" if owed and worth <= 0 else "Nothing owed", "/", over=bool(owed) and worth <= 0),
        _ratio_tile(h.debt_to_cash, as_of, f"{fmt(owed, 0)} owed against {fmt(cash, 0)} cash you own",
                    "No cash to set it against" if owed else "Nothing owed", "/"),
        _ratio_tile(h.loan_payments_to_income, as_of, f"{fmt(loans, 0)} a month of {fmt(income or ZERO, 0)} income",
                    "Set your income categories to measure it" if loans and not income else "No loan payments left",
                    "#loans-list"),
    ]


@router.get("/recurring")
async def recurring_page(request: Request):
    c = container(request)
    day = today()
    c.planning.match_payments(day)
    labels = _labels(c)
    linked = c.planning.linked_transaction_ids()
    rows = [_row(c, item, labels, day, linked) for item in c.planning.items(RECURRING_KINDS)]
    rows.sort(key=lambda row: (row["next"] is None,
                              row["next"].due_date if row["next"] else "",
                              row["item"].name.casefold()))
    stopped = c.planning.items(RECURRING_KINDS, active_only=False)
    stopped = [i for i in stopped if not i.active]
    subscriptions = sum((r["per_year"] for r in rows if r["item"].kind == PlanKind.SUBSCRIPTION), ZERO)
    health = c.health.at(day)
    monthly_out = health.bills_a_month
    fixed = health.fixed_costs_to_income
    fixed_tiles = [_ratio_tile(fixed, fmt_date(day),
                               f"{fmt(fixed.part, 0)} a month of {fmt(fixed.whole or ZERO, 0)} income · bills, subscriptions and loans",
                               "Set your income categories to measure it" if fixed.part else "No bills, subscriptions or loans yet",
                               "#recurring-totals")]
    monthly_in = sum((r["per_year"] for r in rows if r["item"].is_income), ZERO) / 12
    bill_bars = charts.bars([{"label": r["item"].name, "value": r["per_year"] / 12,
                              "note": r["item"].kind_label + (" · " + r["category"] if r["category"] else "")}
                             for r in rows if not r["item"].is_income])
    return render(request, "planning/recurring.html", tabs=TABS, plan_tab="recurring", rows=rows, stopped=stopped,
                  answer=page_status.recurring(monthly_out, fixed.percent),
                  bill_bars=bill_bars, fixed_tiles=fixed_tiles,
                  recurring_kpis=kpis.recurring(
                      monthly_out=monthly_out, fixed=fixed, limit=c.health.limit_values().get(fixed.key),
                      band=c.health.band(fixed.key, fixed.percent) if fixed.percent is not None else None,
                      subscriptions_per_year=subscriptions,
                      due_count=sum(len(r["due"]) for r in rows if not r["item"].is_income),
                      due_total=sum((c.planning.amount_in_base(r["item"], p.amount, day)
                                     for r in rows if not r["item"].is_income for p in r["due"]), ZERO)),
                  suggestions=c.planning.suggestions(day), dismissed=c.planning.dismissed_suggestions(),
                  subscriptions_per_year=subscriptions,
                  monthly_out=monthly_out, monthly_in=monthly_in, labels=labels, as_of=fmt_date(day))


UPCOMING_GROUPS = {"bills": "Bills", "instalments": "Instalments", "gameya": "Gam'eya", "income": "Income"}
MARKS_PER_DAY = 3  # a day cell shows three marks, then "+n"


def _month_grid(month, first, last, day, show: str, chosen: str) -> list[list[dict | None]]:
    """The month as weeks starting Saturday (A12.1.12): each day with its marks; figures come from the service."""
    order = [(visuals.WEEK_STARTS_ON + i) % 7 for i in range(7)]  # not money
    weeks, week = [], [None] * order.index(first.weekday())  # not money
    cursor, today_text = first, fmt_date(day)
    paydays = set(month.paydays)
    while cursor <= last:
        key = fmt_date(cursor)
        entries = [e for e in month.on(key) if show == "all" or e.group == show]
        week.append({"day": cursor.day, "date": key, "today": key == today_text, "chosen": key == chosen,
                     "payday": key in paydays, "short": key == month.short_on, "entries": entries[:MARKS_PER_DAY],
                     "more": max(len(entries) - MARKS_PER_DAY, 0),  # not money
                     "late": any(e.state == "late" for e in entries)})
        if len(week) == 7:
            weeks.append(week)
            week = []
        cursor += timedelta(days=1)  # not money
    if week:
        weeks.append(week + [None] * (7 - len(week)))  # not money
    return weeks


@router.get("/upcoming.ics")
async def upcoming_calendar_file(request: Request):
    """NF-7AR4: the next three months' open payments as a calendar file; it leaves only when the person saves it."""
    from fastapi.responses import Response
    from lightning.planning.ics import payments_ics
    c = container(request)
    day = today()
    c.planning.match_payments(day)
    return Response(payments_ics(c.planning, c.gameya, day), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="lightning-payments.ics"',
                             "Cache-Control": "no-store"})


@router.get("/upcoming")
async def upcoming_page(request: Request):
    """What do I still have to pay this month, and on which days? (NF-7AR)"""
    from lightning.planning.calendar import month_calendar
    c = container(request)
    day = today()
    c.planning.match_payments(day)
    month = str(request.query_params.get("month", "")) or month_of(day)
    try:
        first, last = parse_month(month)
    except ValidationError:
        month = month_of(day)
        first, last = parse_month(month)
    show = str(request.query_params.get("show", "all"))
    show = show if show in UPCOMING_GROUPS else "all"
    cal = month_calendar(c.planning, c.gameya, month, day, c.forecaster)
    chosen = str(request.query_params.get("day", ""))
    if not (chosen[:7] == month and len(chosen) == 10):
        # The answer first: the next day that still asks for money (a late one before it), else today or the 1st.
        open_days = [e.date for e in cal.entries if not e.incoming and e.left > ZERO
                     and (e.date >= fmt_date(day) or e.state == "late")]
        chosen = open_days[0] if open_days else fmt_date(day) if first <= day <= last else fmt_date(first)
    shown = [e for e in cal.on(chosen) if show == "all" or e.group == show]
    name = calendar.month_name[first.month]
    previous_name = calendar.month_name[(first - timedelta(days=1)).month]  # not money
    change, last_total = cal.change_from_last_month, cal.last_month_total
    compared = ("" if not last_total else f"The same as {previous_name}" if not change
                else f"{fmt(change, 0)} more than {previous_name}" if change > 0
                else f"{fmt(change, 0).lstrip('-−')} less than {previous_name}")
    lead = kpis.card(
        f"Left to pay in {name}", cal.left_to_pay,
        kpis.compare(f"of {fmt(cal.month_total, 0)} due in {name}", f"{fmt(cal.already_paid, 0)} paid", "good"),
        tone="out", visual=kpis.segments([("Paid", cal.already_paid, "hold"), ("Left", cal.left_to_pay, "out")]),
        line_=kpis.line(compared), needs=any(e.state == "late" for e in cal.entries)) if cal.month_total else None
    back = urlencode({"month": month, "day": chosen, **({"show": show} if show != "all" else {})})
    return render(request, "planning/upcoming.html", tabs=TABS, plan_tab="upcoming", cal=cal, lead=lead,
                  answer=page_status.upcoming(cal.left_to_pay, name, cal.days_to_pay),
                  weeks=_month_grid(cal, first, last, day, show, chosen), weekdays=[visuals.WEEKDAYS[(visuals.WEEK_STARTS_ON + i) % 7] for i in range(7)],  # not money
                  month=month, month_name=f"{name} {first.year}", show=show, groups=UPCOMING_GROUPS,
                  chosen=chosen, shown=shown, day_back="/plan/upcoming?" + back,
                  previous_month=month_of(first - timedelta(days=1)), next_month=month_of(last + timedelta(days=1)),  # not money
                  this_month=month_of(day))


@router.get("/loans")
async def loans_page(request: Request):
    c = container(request)
    day = today()
    c.planning.match_payments(day)
    labels = _labels(c)
    loans = [{"item": item, "progress": c.planning.loan_progress(item, day), "schedule": describe(item),
              "account": labels["accounts"].get(item.account_id)} for item in c.planning.items((PlanKind.LOAN,))]
    for entry in loans:
        entry["meter"] = charts.meter(entry["progress"]["paid_amount"], entry["progress"]["total_amount"])
    summary = keynotes.loans_summary(loans)  # its words become the Lead's line; a note never forms a row (A09)
    still_to_pay = c.planning.what_you_owe(day).loans_still_to_pay
    paid = sum((e["progress"]["paid_amount"] for e in loans), ZERO)
    borrowed = sum((e["progress"]["total_amount"] for e in loans), ZERO)
    # The page's answer is a Lead (A07): what is left to pay, against what was borrowed, paid and left as its picture.
    lead = kpis.card("Loans still to pay", still_to_pay,
                     kpis.compare(f"of {fmt(borrowed, 0)} in {counted(len(loans), 'loan', 'loans')}",
                                  f"{fmt(paid, 0)} paid", "good"),
                     tone="out", visual=kpis.segments([("Paid", paid, "hold"), ("Left", borrowed - paid, "out")]),
                     line_=kpis.line(summary["title"] if summary else ""),  # "Paid off on …" or "2 loan payments due now"
                     needs=bool(summary and summary["tone"] == "attention")) if loans else None
    health = c.health
    return render(request, "planning/loans.html", tabs=TABS, plan_tab="loans", loans=loans, lead=lead,
                  answer=page_status.loans(still_to_pay, len(loans)),
                  debt_tiles=_debt_tiles(health.at(day), fmt_date(day)),
                  debt_kpis=kpis.debt(health.at(day), limits=health.limit_values(), band=health.band, as_of=fmt_date(day)),
                  still_to_pay=still_to_pay, as_of=fmt_date(day))


@router.get("/reserves")
async def reserves_page(request: Request):
    return render(request, "reserves.html", tabs=TABS, plan_tab="reserves", **reserve_routes._context(request))


# ------------------------------------------------------------------ items
def _purchase_form(request, values=None, quote=None, error="", status_code=200, error_field=""):
    c = container(request)
    return render(request, "planning/purchase.html", values=values or {"name": "", "price": "", "fee": "",
                  "months": "", "first_date": fmt_date(today()), "account_id": ""}, quote=quote,
                  accounts=[a for a in _paying_accounts(c) if a.currency == c.base_currency],
                  error=error, status_code=status_code, error_field=error_field, edit_url="/plan/purchases/new?" + urlencode(values or {}))


@router.get("/purchases/new")
async def purchase_form(request: Request):
    q = request.query_params
    values = {key: str(q.get(key, "")) for key in ("name", "price", "fee", "months", "first_date", "account_id")} if any(key in q for key in ("name", "price", "months")) else None
    return _purchase_form(request, values)


@router.post("/purchases/new")
async def add_purchase(request: Request):
    from lightning.planning.loan_actions import purchase_quote
    form = await request.form()
    values = {key: str(form.get(key, "")) for key in ("name", "price", "fee", "months", "first_date", "account_id")}
    try:
        if not values["name"].strip():
            raise ValidationError("Name the purchase.", "name")
        quote = purchase_quote(values["price"], values["fee"], values["months"], values["first_date"])
        if form.get("intent") == "save":
            c = container(request)
            submission = None if getattr(c, "is_journal", False) else str(form.get("submission", ""))
            payload = {key: values[key] for key in ("name", "price", "fee", "months", "first_date", "account_id")}
            with settled_save(request, c):
                if not c.transactions.form_seen(submission, payload):  # a resent form saves nothing more (2AD)
                    c.planning.create_purchase(**(values | {"fee": quote["fee"]}))
                    c.transactions.remember_form(submission, payload)
            return redirect("/plan/loans", "Instalment plan added. Record each payment when it leaves your account.")
        return _purchase_form(request, values, quote)
    except (LightningError, ValueError) as exc:
        return _purchase_form(request, values, error=exc.message if isinstance(exc, LightningError) else "Check the amounts and dates.", status_code=400, error_field=exc.field if isinstance(exc, LightningError) else "")


def _early_form(request, item_id, values=None, preview=None, error="", status_code=200, error_field=""):
    c = container(request)
    item = c.planning.get(item_id)
    progress = c.planning.loan_progress(item)
    values = values or {"principal": str(progress["still_to_pay"]), "fee": "", "date_paid": fmt_date(today()),
                        "account_id": str(item.account_id or "")}
    return render(request, "planning/early_payment.html", item=item, progress=progress, values=values, preview=preview,
                  accounts=[a for a in _paying_accounts(c) if a.currency == c.base_currency],
                  error=error, status_code=status_code, error_field=error_field,
                  edit_url=f"/plan/items/{item_id}/early-payment?" + urlencode(values))


@router.get("/items/{item_id:int}/early-payment")
async def early_payment_form(request: Request, item_id: int):
    q = request.query_params
    values = {key: str(q.get(key, "")) for key in ("principal", "fee", "date_paid", "account_id")} if "principal" in q else None
    return _early_form(request, item_id, values)


@router.post("/items/{item_id:int}/early-payment")
async def early_payment(request: Request, item_id: int):
    from lightning.planning.loan_actions import preview_early_payment
    c = container(request)
    form = await request.form()
    values = {key: str(form.get(key, "")) for key in ("principal", "fee", "date_paid", "account_id")}
    try:
        preview = preview_early_payment(c.planning, item_id, values["principal"], values["fee"], values["date_paid"])
        with settled_save(request, container(request)):
            if form.get("intent") == "record":
                c.planning.record_early_payment(item_id, **(values | {"fee": preview["fee"]}),
                                                  expected_remaining=form.get("expected_remaining", ""))
                return redirect("/plan/loans", "Loan payment recorded. The remaining schedule is updated.")
        return _early_form(request, item_id, values, preview)
    except (LightningError, ValueError) as exc:
        return _early_form(request, item_id, values, error=exc.message if isinstance(exc, LightningError) else "Choose a paying account.", status_code=400, error_field=exc.field if isinstance(exc, LightningError) else "")


def _item_form(request: Request, c, values: dict, item=None, error: str = "", error_field: str = "",
               status_code: int = 200, back: str = "/plan/recurring", form_action: str | None = None,
               promotion=None):
    kind = values.get("kind") or PlanKind.BILL.value
    movement = Movement.INFLOW if kind == PlanKind.INCOME.value else Movement.OUTFLOW
    kinds = ([(kind, KIND_LABELS[PlanKind(kind)])] if promotion else
             [(PlanKind.LOAN.value, "Loan or installment plan")] if kind == PlanKind.LOAN.value else [
        (k.value, KIND_LABELS[k]) for k in RECURRING_KINDS]
             )
    accounts = _paying_accounts(c)
    selected_account = next((a for a in accounts if str(a.id) == str(values.get("account_id", ""))), None)
    return render(request, "planning/item_form.html", status_code=status_code, values=values, item=item,
                  has_history=bool(item) and c.planning.has_history(item.id),
                  installment=bool(item) and c.planning.is_installment_purchase(item.id),
                  kinds=kinds, is_loan=kind == PlanKind.LOAN.value,
                  frequencies=[(f.value, FREQUENCY_LABELS[f]) for f in Frequency],
                  weekend_moves=[(m.value, WEEKEND_MOVE_LABELS[m]) for m in WeekendMove],
                  accounts=accounts, matching_open=_matching_open(values, kind, error_field),
                  categories=_category_options(c, movement), counterparties=c.counterparties.list_active(),
                  error=error, error_field=error_field, back=back, form_action=form_action,
                  promotion=promotion, promotion_currency=promotion["currency"] if promotion else None,
                  amount_currency=selected_account.currency if selected_account else c.transactions.base_currency)


def _matching_open(values: dict, kind: str, error_field: str | None) -> bool:
    """The Matching disclosure opens only when a setting differs from the default or has an error."""
    if error_field in ("match_window_days", "match_tolerance_pct", "weekend_move"):
        return True
    default_tolerance = "1" if kind == PlanKind.LOAN.value else "10"
    defaults = {"match_window_days": "7", "match_tolerance_pct": default_tolerance, "weekend_move": "none"}
    return any(str(values.get(key) or default) != default for key, default in defaults.items())


@router.get("/from-transaction/{txn_id:int}")
async def promote_transaction_form(request: Request, txn_id: int):
    c = container(request)
    try:
        source = c.planning.from_transaction(txn_id)
    except LightningError as exc:
        return redirect(f"/transactions/{txn_id}", exc.message)
    return _item_form(request, c, source["values"],
                      back=f"/transactions/{txn_id}", form_action=f"/plan/from-transaction/{txn_id}",
                      promotion=source)


@router.post("/from-transaction/{txn_id:int}")
async def promote_transaction(request: Request, txn_id: int):
    c = container(request)
    try:
        source = c.planning.from_transaction(txn_id)
    except LightningError as exc:
        return redirect(f"/transactions/{txn_id}", exc.message)
    form = await request.form()
    values = _form_values(form)
    back = f"/transactions/{txn_id}"
    if values["start_date"] == source["values"]["start_date"] and values["frequency"] == "MONTHLY":
        values["month_day"] = source["values"]["month_day"]
    if values["kind"] != source["values"]["kind"]:
        return _item_form(request, c, values, error="Keep the transaction's income or bill type.",
                          error_field="kind", status_code=400, back=back,
                          form_action=f"/plan/from-transaction/{txn_id}", promotion=source)
    try:
        with settled_save(request, container(request)):
            item_id = c.planning.create(**_save_values(c, values))
            message = f"{values['name']} added from {source['transaction'].ref}."
            if str(form.get("past_due", "paid")) == "paid":
                moved = c.planning.start_after_paid(item_id)
                if moved:
                    message += f" Already paid, so the next one is due {moved}."
    except LightningError as exc:
        return _item_form(request, c, values, error=exc.message, error_field=exc.field or "", status_code=400,
                          back=back, form_action=f"/plan/from-transaction/{txn_id}", promotion=source)
    return redirect("/plan/recurring", " ".join(x for x in (message, c.health.commitments_note(values["kind"])) if x))


@router.get("/items/new")
async def new_item(request: Request):
    c = container(request)
    q = request.query_params
    values = {k: str(q.get(k, "")) for k in FIELDS}
    values["kind"] = (values["kind"] or "BILL").upper()
    values["frequency"] = values["frequency"] or "MONTHLY"
    values["interval_count"] = values["interval_count"] or "1"
    values["start_date"] = values["start_date"] or fmt_date(today())
    values["weekend_move"] = values["weekend_move"] or "none"  # a date moves only when you choose it
    values["match_window_days"] = values["match_window_days"] or "7"
    values["match_tolerance_pct"] = values["match_tolerance_pct"] or ("1" if values["kind"] == "LOAN" else "10")
    if values["kind"] == "LOAN" and not values["category_id"]:
        try:
            values["category_id"] = str(c.categories.get_by_code(LOAN_CATEGORY).id)
        except LightningError:
            pass
    back = "/plan/loans" if values["kind"] == "LOAN" else "/plan/recurring"
    return _item_form(request, c, values, back=str(q.get("back", back)))


@router.post("/items")
async def create_item(request: Request):
    c = container(request)
    form = await request.form()
    values = _form_values(form)
    back = _back(form, "/plan/loans" if values["kind"] == "LOAN" else "/plan/recurring")
    try:
        with settled_save(request, container(request)):
            item_id = c.planning.create(**_save_values(c, values))
            message = f"{values['name']} added."
            if str(form.get("past_due", "paid")) == "paid":
                moved = c.planning.start_after_paid(item_id)
                if moved:
                    message = f"{values['name']} added. Already paid, so the next one is due {moved}."
    except LightningError as exc:
        return _item_form(request, c, values, error=exc.message, error_field=exc.field or "", status_code=400, back=back)
    return redirect(back, " ".join(x for x in (message, c.health.commitments_note(values["kind"])) if x))


@router.get("/items/{item_id:int}/sheet")
async def item_sheet(request: Request, item_id: int):
    """One bill sheet for every tab (3G6): a bill, subscription, loan or income with its next date, what is due, the
    last payments, Mark paid and Edit. Recurring and Cash planning open it. Figures are PlanningService's own."""
    c = container(request)
    day = today()
    item = c.planning.get(item_id)
    labels = _labels(c)
    row = _row(c, item, labels, day, c.planning.linked_transaction_ids())
    payments = c.planning.payments(item, fmt_date(day), day)
    paid = [p for p in reversed(payments) if p.status == PaymentStatus.PAID][:3]
    back = str(request.query_params.get("back", "/plan/recurring"))
    back = back if back.startswith("/") and not back.startswith("//") else "/plan/recurring"
    return render(request, "planning/item_sheet.html", r=row, paid=paid, back=back,
                  late={(p.due_date): p.days_late(day) for p in row["due"]})


@router.get("/items/{item_id:int}/edit")
async def edit_item(request: Request, item_id: int):
    c = container(request)
    item = c.planning.get(item_id)
    party = c.counterparties.get(item.counterparty_id)["name"] if item.counterparty_id else ""
    values = {"kind": item.kind.value, "name": item.name, "amount": f"{item.amount:.2f}",
              "frequency": item.frequency.value, "interval_count": str(item.interval_count),
              "start_date": item.start_date, "end_date": item.end_date or "",
              "payment_count": str(item.payment_count or ""), "account_id": str(item.account_id or ""),
              "category_id": str(item.category_id or ""), "counterparty": party,
              "principal": f"{item.principal:.2f}" if item.principal else "", "notes": item.notes,
              "weekend_move": item.weekend_move.value,
              "match_window_days": str(item.match_window_days),
              "match_tolerance_pct": str(item.match_tolerance_pct)}
    back = "/plan/loans" if item.kind == PlanKind.LOAN else "/plan/recurring"
    return _item_form(request, c, values, item=item, back=back)


@router.post("/items/{item_id:int}/edit")
async def update_item(request: Request, item_id: int):
    c = container(request)
    item = c.planning.get(item_id)
    form = await request.form()
    values = _form_values(form)
    back = _back(form, "/plan/loans" if item.kind == PlanKind.LOAN else "/plan/recurring")
    try:
        with settled_save(request, container(request)):
            c.planning.update(item_id, **_save_values(c, values))
    except LightningError as exc:
        return _item_form(request, c, values, item=item, error=exc.message, error_field=exc.field or "",
                          status_code=400, back=back)
    return redirect(back, " ".join(x for x in (f"{values['name']} saved.", c.health.commitments_note(item.kind.value)) if x))


@router.post("/suggestions/{counterparty_id:int}/restore")
async def restore_suggestion(request: Request, counterparty_id: int):
    c = container(request)
    with settled_save(request, container(request)):
        value = c.planning.restored_suggestion_setting(counterparty_id)
        c.settings.set("recurring_not_suggested", value)
    return redirect("/plan/recurring", "Suggestion restored.")


@router.post("/suggestions/{counterparty_id:int}/not-recurring")
async def not_recurring(request: Request, counterparty_id: int):
    name = container(request).planning.not_recurring(counterparty_id)
    return redirect("/plan/recurring", f"{name} will not be suggested again.")


@router.post("/items/{item_id:int}/amount")
async def set_item_amount(request: Request, item_id: int):
    c = container(request)
    form = await request.form()
    item = c.planning.get(item_id)
    try:
        with settled_save(request, container(request)):
            c.planning.set_amount(item_id, str(form.get("amount", "")))
    except LightningError as exc:
        return redirect(_back(form, "/plan/recurring"), exc.message)
    return redirect(_back(form, "/plan/recurring"), " ".join(x for x in (
        f"{item.name} is now planned at {fmt(to_decimal(str(form.get('amount')), 'amount'))}.",
        c.health.commitments_note(item.kind.value)) if x))


@router.post("/items/{item_id:int}/delete")
async def delete_item(request: Request, item_id: int):
    c = container(request)
    form = await request.form()
    item = c.planning.get(item_id)
    with settled_save(request, container(request)):
        message = c.planning.remove(item_id)
    return redirect(_back(form, "/plan/loans" if item.kind == PlanKind.LOAN else "/plan/recurring"), message)


# --------------------------------------------------------------- payments
def _afford_account_answer(c, request, afford, day):
    """Can I afford this? on a chosen account and date: that account's day-end balance on that date, scheduled-only,
    beside the plan answer, with the assumptions and a link to record it only if the person confirms."""
    from lightning.planning.afford import account_check
    from lightning.planning.dated_cash import dated_cash_forecast
    raw = str(request.query_params.get("afford_account", ""))
    if afford is None or not raw.isdigit():
        return None
    account = next((a for a in c.accounts.list(active_only=True) if a.id == int(raw)), None)
    if account is None or account.currency != c.base_currency:
        return None
    try:
        on = parse_date(str(request.query_params.get("afford_date", "")) or fmt_date(day))
    except (ValueError, LightningError):
        return None
    on = max(on, day)
    end = max(on, day + timedelta(days=90))
    payments, events = c.forecaster.scheduled_inputs(day, end)
    projection = dated_cash_forecast(c.reporting, payments, events, day, end)
    answer = account_check(projection.account_series, account.id, fmt_date(on), afford.amount, account.name)
    return {"answer": answer, "account": account, "record_url": "/accounts/%d/transaction/new?%s" % (
        account.id, urlencode({"kind": "out", "amount": str(afford.amount), "date": fmt_date(on),
                               "return_to": "/plan"}))}


def _payment_effects(c, item, payment, paid_on) -> dict:
    """What recording this payment would change, before it is recorded (NF-3AZ4): the bill's reserve and the
    category's budget line for the month it would be paid in. Read-only."""
    owed = payment.still_owed
    reserve = c.reserves.bill_reserve(item.id)
    effects = {"owed": owed, "reserve": None, "budget": None}
    if reserve:
        used = min(reserve["effective_allocated"], owed)
        effects["reserve"] = {"name": reserve["name"], "before": reserve["effective_allocated"], "used": used,
                              "after": reserve["effective_allocated"] - used}
    if item.category_id and not item.is_income:
        month = str(paid_on)[:7]
        view = c.budgets.month_view(month, schedule=c.schedules.view())
        line = next((l for sec in view.sections for l in sec.lines if l.category_id == item.category_id), None)
        if line is not None and line.budget is not None:
            effects["budget"] = {"name": line.name, "month": month, "left_before": line.remaining,
                                 "left_after": line.remaining - owed, "over": line.remaining - owed < 0}
    return effects


@router.get("/items/{item_id:int}/pay")
async def pay_form(request: Request, item_id: int, error: str = ""):
    c = container(request)
    item = c.planning.get(item_id)
    due = str(request.query_params.get("due", ""))
    payment = next((p for p in c.planning.payments(item, due or fmt_date(today()), today()) if p.due_date == due), None)
    if not payment:
        return redirect("/plan", "That payment is not on the schedule.")
    exact = c.planning.candidates(payment, any_account=True)  # a person reviews: any cash account counts
    others = c.planning.plausible_candidates(payment)
    linked = c.planning.linked_transaction_ids()
    currency = c.accounts.get(item.account_id).currency if item.account_id else c.transactions.base_currency
    exact_open = [r for r in exact if r["id"] not in linked]
    effects = _payment_effects(c, item, payment, min(payment.due_date, fmt_date(today()))) if payment.outstanding else None
    return render(request, "planning/pay.html", item=item, payment=payment, effects=effects, has_match=bool(exact_open),
                  exact=[r for r in exact if r["id"] not in linked], others=[r for r in others if r["id"] not in linked][:8],
                  accounts=_paying_accounts(c), currency=currency, bill_reserve=c.reserves.bill_reserve(item.id),
                  back=str(request.query_params.get("back", "/plan")), today=fmt_date(today()), error=error)


@router.post("/items/{item_id:int}/pay")
async def settle_payment(request: Request, item_id: int):
    c = container(request)
    form = await request.form()
    due = str(form.get("due", ""))
    action = str(form.get("outcome", ""))
    back = _back(form, "/plan")
    item = c.planning.get(item_id)
    try:
        with settled_save(request, container(request)):
            if action == "link":
                c.planning.mark_paid(item_id, due, int(str(form.get("transaction_id", "0"))))
                message = f"{item.name} · {due} marked paid."
            elif action == "record":
                due_payment = next((p for p in c.planning.payments(item, due, today()) if p.due_date == due), None)
                if due_payment and due_payment.outstanding and not form.get("different_payment") and any(
                        r["id"] not in c.planning.linked_transaction_ids()
                        for r in c.planning.candidates(due_payment, any_account=True)):
                    raise LightningError("A payment that matches this bill is already recorded. Link it instead, "
                                         "or tick \"This is a different payment\" to record a second one.")
                c.planning.record_payment(item_id, due, str(form.get("date_paid", "")), str(form.get("amount", "")),
                                          int(str(form.get("account_id"))) if str(form.get("account_id", "")).isdigit() else None)
                message = f"{item.name} · {due} recorded and marked paid."
                paid = to_decimal(str(form.get("amount", "")), "amount")
                if paid != item.amount and item.frequency != Frequency.ONCE:
                    message += (f" You paid {fmt(paid)} instead of {fmt(item.amount)}; Recurring offers to use "
                                f"{fmt(paid)} from now on.")
            elif action == "skip":
                c.planning.skip(item_id, due)
                message = (f"{item.name} · {due} moved to the end of the loan." if item.kind == PlanKind.LOAN
                           else f"{item.name} · {due} skipped.")
            elif action == "reopen":
                was_skipped = any(p.due_date == due and p.status == PaymentStatus.SKIPPED
                                  for p in c.planning.payments(item, due, today()))
                c.planning.reopen(item_id, due)
                message = f"{item.name} · {due} is " + ("back on the schedule." if was_skipped else "unpaid again.")
            else:
                raise LightningError("Choose how this payment was settled.")
    except LightningError as exc:
        return redirect(f"/plan/items/{item_id}/pay?" + urlencode({"due": due, "back": back}), exc.message)
    return redirect(back, message)


def _catch_key(payment) -> str:
    return f"{payment.item.id}:{payment.due_date}"


@router.get("/catch-up")
async def catch_up(request: Request):
    """IV-12AA5: each late payment in turn, paid (on the pay page: a matching payment first, then the day and the
    account) or not yet, then a summary of what this catch-up changed, with Undo. The list is fixed when it
    starts (``start``), so a bill paid along the way stays in the summary; ``later`` holds the ones left for now."""
    c = container(request)
    day = today()
    q = request.query_params
    if not q.get("start"):
        late = late_payments(c.planning, day)
        if not late:
            return redirect("/plan", "Nothing is late.")
        return redirect("/plan/catch-up?" + urlencode({"start": ",".join(_catch_key(p) for p in late)}))
    start = [key for key in str(q.get("start", "")).split(",") if key]
    later = [key for key in str(q.get("later", "")).split(",") if key in start]
    here = "/plan/catch-up?" + urlencode({"start": ",".join(start), **({"later": ",".join(later)} if later else {})})
    rows = []
    for key in start:
        item_id, _, due = key.partition(":")
        try:
            item = c.planning.get(int(item_id))
        except (LightningError, ValueError):
            continue
        payment = next((p for p in c.planning.payments(item, due, day) if p.due_date == due), None)
        if payment is not None:
            rows.append({"key": key, "item": item, "payment": payment, "later": key in later})
    waiting = [r for r in rows if r["payment"].outstanding and not r["later"]]
    if waiting:
        current = waiting[0]
        p = current["payment"]
        currency = c.accounts.get(p.item.account_id).currency if p.item.account_id else c.base_currency
        return render(request, "planning/catch_up.html", step=current, number=rows.index(current) + 1, total=len(rows),  # not money: counts and keys
                      amount=p.still_owed, currency=currency, late_days=p.days_late(day),
                      pay_href=f"/plan/items/{p.item.id}/pay?" + urlencode({"due": p.due_date, "back": here}),
                      later_href="/plan/catch-up?" + urlencode({"start": ",".join(start),
                                                                "later": ",".join(later + [current["key"]])}),  # not money: counts and keys
                      summary=None, here=here)
    summary = {"paid": [r for r in rows if r["payment"].status == PaymentStatus.PAID],
               "skipped": [r for r in rows if r["payment"].status == PaymentStatus.SKIPPED],
               "not_yet": [r for r in rows if r["payment"].outstanding]}
    for r in summary["paid"]:
        p = r["payment"]
        r["paid"] = c.planning.amount_in_base(p, p.paid_amount if p.paid_amount is not None else p.amount, day)
    summary["paid_total"] = sum((r["paid"] for r in summary["paid"]), ZERO)
    return render(request, "planning/catch_up.html", step=None, summary=summary, total=len(rows), here=here)


@router.get("/inputs")
async def forecast_inputs(request: Request):
    c = container(request)
    day = today()
    return render(request, "planning/inputs.html", notes=c.freshness.for_forecast(day),
                  note_days=lambda note: c.freshness.days_old(note, day))


@router.get("/scenarios")
async def scenario_page(request: Request):
    from lightning.planning.scenarios import compare_scenario, occurrence_key
    c = container(request)
    day, end = today(), today() + timedelta(days=90)
    values = {key: str(request.query_params.get(key, '')) for key in
              ('income', 'delay', 'purchase', 'purchase_date', 'account_id', 'bill', 'bill_amount')}
    # One question at a time (F10, r24): the chosen kind, else the one that already has values, else a purchase.
    what = str(request.query_params.get("what", ""))
    if what not in ("income", "purchase", "bill"):
        what = "income" if values["income"] else "bill" if values["bill"] else "purchase"
    error = ''
    try:
        comparison = compare_scenario(c.forecaster, day, end, **values)
    except LightningError as exc:
        error = exc.message
        comparison = compare_scenario(c.forecaster, day, end)
    payments, _ = c.forecaster.scheduled_inputs(day, end)
    return render(request, "planning/scenarios.html", comparison=comparison, values=values, error=error, what=what,
                  day=str(day), end=str(end), payments=payments, occurrence_key=occurrence_key,
                  accounts=_paying_accounts(c))


@router.get("/bill-alerts/{key}")
async def bill_alert_page(request: Request, key: str):
    from lightning.workflows.bill_alerts import bill_alerts
    c = container(request)
    alert = next((row for row in bill_alerts(c, today()) if row['key'] == key), None)
    if alert is None:
        return render(request, "not_found.html", status_code=404, message="This bill alert no longer applies.")
    return render(request, "planning/bill_alert.html", alert=alert)
