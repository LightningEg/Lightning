"""Cash planning: Plan · Recurring · Loans · Reserves."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from lightning.categories.domain import Direction, Movement
from lightning.core.dates import fmt_date, month_of, parse_date, parse_month, today
from lightning.core.errors import LightningError, ValidationError
from lightning.core.figures import label
from lightning.core.money import ZERO, fmt, to_decimal
from lightning.planning.domain import (FREQUENCY_LABELS, KIND_LABELS, RECURRING_KINDS, WEEKEND_MOVE_LABELS, Frequency,
                                       PaymentStatus, PlanKind, WeekendMove, per_year)
from lightning.planning.forecast import emergency_fund
from lightning.planning.schedule import describe
from lightning.planning.service import LOAN_CATEGORY

from .. import charts, keynotes, kpis, visuals, status as page_status
from ..web import container, redirect, render
from . import reserves as reserve_routes

router = APIRouter(prefix="/plan")

FIELDS = ("kind", "name", "amount", "frequency", "interval_count", "start_date", "end_date", "payment_count",
          "account_id", "category_id", "counterparty", "principal", "notes", "weekend_move",
          "match_window_days", "match_tolerance_pct")
TABS = (("plan", "Plan", "/plan"), ("recurring", "Recurring", "/plan/recurring"),
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
    return {"accounts": accounts, "categories": categories}


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
            "per_year": per_year, "reserve_links": reserve_links, "review_next": review_next}


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
    status = page_status.cash_plan(forecast.safe_to_spend, forecast.next_income_date, has_income)
    afford, afford_error = None, ""
    raw_afford = request.query_params.get("afford", "").replace(",", "").strip()
    if raw_afford:
        from lightning.planning.afford import can_afford
        try:
            afford = can_afford(Decimal(raw_afford), forecast.safe_to_spend, forecast.free_cash, forecast.next_income_date)
        except (ArithmeticError, ValueError):
            afford_error = "Type an amount above zero."
    cash = (_phone_cash(c, forecast, next_payments, late, position, day)
            if getattr(request.state, "phone", False) else None)
    return render(request, "planning/plan.html", tabs=TABS, plan_tab="plan", forecast=forecast, owe=owe, has_income=has_income,
                  lead=lead, needs=needs, status=status, cash=cash, afford=afford, afford_error=afford_error,
                  afford_amount=raw_afford,
                  gameya_owed=position.gameya_still_to_pay,
                  notes=[], plan=plan, stats=stats, kpi_cards=kpi_cards, forecast_chart=visuals.forecast_trend(forecast),
                  next_payments=next_payments, late_days=late_days, as_of=fmt_date(day), window_end=fmt_date(window_end),
                  has_items=bool(c.planning.items()), labels=_labels(c), zakat=c.zakat.forecast(day))


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
         "badge": {"tone": "flat", "text": f"{len(plan['before_income'])} payment{'s' if len(plan['before_income']) != 1 else ''}"},
         "sub": f"Next: {nxt.item.name} · {nxt.due_date}" if nxt else "Nothing is due before then",
         "href": "#plan-next"},
        {"key": "low", "surface": "over" if low and low.closing < 0 else "hold", "label": "Lowest point ahead", "value": low.closing if low else None, "kind": "money",
         "empty": "—", "badge": {"tone": "over" if low and low.closing < 0 else "flat", "text": low.month if low else "—"},
         "sub": (f"Runs short in {short.month}: the month ends below your reserves" if short
                 else "" if low else "Add your bills and income to see it"),
         "spark": plan["forecast_spark"], "spark_tone": "over" if low and low.closing < 0 else "hold", "href": "#plan-forecast"},
    ]


PHONE_ROWS_SHOWN = 8


def _phone_cash(c, f, next_payments, late, position, day) -> dict:
    """What the phone's Cash planning adds to the PC's figures (phone overhaul 2026-10-22, "What leaves before payday,
    and am I covered?"): the Due before payday hero with its coverage sentences, the dated list that ends with payday,
    and the Free cash and Reserves tiles. Figures are the ones Safe to spend already uses, so the hero is the working's
    Due before payday row; sentences go to the template as pattern and values (status.sentence)."""
    sentence = page_status.sentence
    until = f.next_income_date
    due = -dict(f.safe_to_spend_parts).get(label("payments_before_next_income"), ZERO)

    def base(p) -> Decimal:
        try:
            return c.planning.amount_in_base(p, p.still_owed, day)
        except ValidationError:  # no rate yet: show the amount as scheduled rather than hide the row
            return p.still_owed

    def when(date_text: str) -> dict:
        days = (parse_date(date_text) - day).days
        return sentence("today") if days <= 0 else sentence("tomorrow") if days == 1 else sentence("in {n} days", n=days)

    def row(p) -> dict:
        late_days = p.days_late(day)
        return {"name": p.item.name, "kind": KIND_LABELS[p.item.kind] if not p.item.is_income else "Payday",
                "income": p.item.is_income, "date": p.due_date, "when": when(p.due_date), "late": late_days,
                "late_text": sentence("Late · 1 day" if late_days == 1 else "Late · {n} days", n=late_days) if late_days else None,
                "amount": base(p), "estimated": False, "popup": True,
                "href": f"/plan/items/{p.item.id}/pay?due={p.due_date}&back=%2Fplan"}

    # Late and due-today payments first (their money is already out of Free cash), then what is not due yet before
    # payday, then payday itself, so the gap between them is plain.
    now = [row(p) for p in next_payments if p.status == PaymentStatus.DUE]
    ahead_payments = sorted(f.payments_before_income, key=lambda p: (p.due_date, p.item.name.casefold()))
    ahead = [row(p) for p in ahead_payments]
    payday_payment = next((p for p in f.upcoming if p.item.is_income), None) if until else None
    payday = None
    if payday_payment:
        payday = row(payday_payment)
    elif until and f.average_income:
        payday = {"name": "Payday", "kind": "Payday", "income": True, "date": until, "when": when(until), "late": 0,
                  "late_text": None, "amount": f.average_income, "estimated": True, "popup": False, "href": "/plan/recurring"}
    shown = {(p.item.id, p.due_date) for p in ahead_payments} | (
        {(payday_payment.item.id, payday_payment.due_date)} if payday_payment else set())
    rest = [row(p) for p in next_payments if p.status == PaymentStatus.UPCOMING and (p.item.id, p.due_date) not in shown]

    # The hero's sentences: how many, whether free cash covers them, whether any are late.
    count = len(ahead)
    if until:
        lines = [sentence("Nothing is due before {date}.", date=until) if not count else
                 sentence("1 payment until {date}." if count == 1 else "{n} payments until {date}.", n=count, date=until)]
    else:
        lines = [sentence("Nothing is due in the next 3 months.") if not count else
                 sentence("1 payment in the next 3 months." if count == 1 else "{n} payments in the next 3 months.", n=count)]
    if due > ZERO:
        lines.append(sentence("All covered by free cash.") if f.free_cash >= due else
                     sentence("Free cash is {amt} short of what is due.", amt=fmt(due - f.free_cash, 0)))
    if late:
        lines.append(sentence("1 payment is already late." if len(late) == 1 else "{n} payments are already late.", n=len(late)))

    # Two tiles after the list: Free cash against what is left of it after the bills, and Reserves with the
    # emergency fund in months (the figure Reserves already shows).
    fund = emergency_fund(c.reserves, c.budgets, month_of(day))
    reserves = position.reserves
    after = fmt(f.free_cash - due, 0).replace("-", "−")
    free_sub = f"After bills: {after}" if due > ZERO else ""
    reserve_sub = (f"Emergency fund {fund.months:.1f} months" if fund.months is not None
                   else "Set aside, not spendable" if reserves else "Nothing set aside yet")
    tiles = [{"key": "free", "surface": "hold", "label": label("free_cash"), "value": f.free_cash, "kind": "money",
              "sub": free_sub, "href": "/"},
             {"key": "reserves", "surface": "hold", "label": label("reserves"), "value": reserves, "kind": "money",
              "empty": "—", "sub": reserve_sub, "href": "/plan/reserves"}]
    return {"due": due, "lines": lines, "now": now, "ahead": ahead, "payday": payday, "rest": rest[:PHONE_ROWS_SHOWN],
            "rest_more": max(len(rest) - PHONE_ROWS_SHOWN, 0), "tiles": tiles}


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
                  bill_bars=bill_bars, fixed_tiles=fixed_tiles,
                  suggestions=c.planning.suggestions(day), subscriptions_per_year=subscriptions,
                  monthly_out=monthly_out, monthly_in=monthly_in, labels=labels, as_of=fmt_date(day))


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
    notes = [n for n in (keynotes.loans_summary(loans),) if n]
    return render(request, "planning/loans.html", tabs=TABS, plan_tab="loans", loans=loans, notes=notes,
                  debt_tiles=_debt_tiles(c.health.at(day), fmt_date(day)),
                  still_to_pay=c.planning.what_you_owe(day).loans_still_to_pay, as_of=fmt_date(day))


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
            container(request).planning.create_purchase(**(values | {"fee": quote["fee"]}))
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
        item_id = c.planning.create(**_save_values(c, values))
    except LightningError as exc:
        return _item_form(request, c, values, error=exc.message, error_field=exc.field or "", status_code=400,
                          back=back, form_action=f"/plan/from-transaction/{txn_id}", promotion=source)
    message = f"{values['name']} added from {source['transaction'].ref}."
    if str(form.get("past_due", "paid")) == "paid":
        moved = c.planning.start_after_paid(item_id)
        if moved:
            message += f" Already paid, so the next one is due {moved}."
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
        item_id = c.planning.create(**_save_values(c, values))
    except LightningError as exc:
        return _item_form(request, c, values, error=exc.message, error_field=exc.field or "", status_code=400, back=back)
    message = f"{values['name']} added."
    if str(form.get("past_due", "paid")) == "paid":
        moved = c.planning.start_after_paid(item_id)
        if moved:
            message = f"{values['name']} added. Already paid, so the next one is due {moved}."
    return redirect(back, " ".join(x for x in (message, c.health.commitments_note(values["kind"])) if x))


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
        c.planning.update(item_id, **_save_values(c, values))
    except LightningError as exc:
        return _item_form(request, c, values, item=item, error=exc.message, error_field=exc.field or "",
                          status_code=400, back=back)
    return redirect(back, " ".join(x for x in (f"{values['name']} saved.", c.health.commitments_note(item.kind.value)) if x))


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
    message = c.planning.remove(item_id)
    return redirect(_back(form, "/plan/loans" if item.kind == PlanKind.LOAN else "/plan/recurring"), message)


# --------------------------------------------------------------- payments
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
    return render(request, "planning/pay.html", item=item, payment=payment,
                  exact=[r for r in exact if r["id"] not in linked], others=[r for r in others if r["id"] not in linked][:8],
                  accounts=_paying_accounts(c), currency=currency,
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
        if action == "link":
            c.planning.mark_paid(item_id, due, int(str(form.get("transaction_id", "0"))))
            message = f"{item.name} · {due} marked paid."
        elif action == "record":
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
        return redirect(f"/plan/items/{item_id}/pay?due={due}&back={back}", exc.message)
    return redirect(back, message)
