from __future__ import annotations

import calendar
from datetime import date, timedelta

from decimal import InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, month_of, months_back, parse_date, parse_month, today
from lightning.core.errors import LightningError, ValidationError
from lightning.core.figures import FIGURES, label
from lightning.core.money import ZERO, fmt as _fmt, to_decimal


def fmt(value, places: int = 0, signed: bool = False) -> str:
    """Reporting text rounds to the nearest unit (stored values keep their decimals)."""
    return _fmt(value, places, signed)
from lightning.investments.report import investing_rate, investment_period, saved_and_invested
from lightning.workflows.review import GROUP_LABELS, ReviewInbox, group_of, grouped

from ..web import container, render
from ..web import redirect
from ..periods import Period, parse_period
from .. import keynotes, kpis, status as page_status, visuals
from .sms import read_phone_sms

router = APIRouter()

_ACCOUNT_TYPE_LABELS = {
    AccountType.CASH: "Cash",
    AccountType.BANK: "Bank",
    AccountType.DEPOSIT: "Deposits",
    AccountType.GAMEYA: "Gam'eya",
    AccountType.BROKERAGE: "Brokerage",
    AccountType.PHYSICAL_ASSET: "Physical assets",
    AccountType.OTHER_ASSET: "Other assets",
}


@router.get("/")
async def dashboard(request: Request):
    c = container(request)
    month = str(request.query_params.get("month", month_of(today())))
    first_activity = c.reporting.first_activity_date()
    try:
        period = parse_period(request.query_params, today(), first_activity)
        period_error = ""
    except ValidationError as exc:
        fallback = parse_period({"period": "month", "month": month_of(today())}, today(), first_activity)
        selected = str(request.query_params.get("period", "month"))
        period = Period(selected, "Custom" if selected == "custom" else fallback.label,
                        fallback.start, fallback.end) if selected in {"all", "ytd", "month", "custom"} else fallback
        period_error = exc.message
    first, as_of = period.start, period.end
    accounts = c.accounts.list()
    if not accounts:
        from lightning.samples.profiles import sample_stories
        registry = c.currencies
        held = [row["code"] for row in registry.list()]
        base = c.base_currency
        common = ["USD", "EUR", "SAR", "AED", "GBP", "KWD"]
        names = {row["code"]: row["name"] for row in registry.suggestions()}
        order = [code for code in common if code in names] + [code for code in names if code not in common]
        return render(request, "dashboard/welcome.html", base=base, currencies=c.profile_currencies,
                      currency_choices=[(code, names[code]) for code in order],
                      held_currencies=[base] + [code for code in held if code != base],
                      extra_currencies=[code for code in held if code != base],
                      currencies_done=c.settings.get("setup_currencies_done") == "1",
                      editing_currencies=request.query_params.get("currencies") == "edit",
                      sample_stories=sample_stories(WELCOME_SAMPLES))
    # Every position figure comes from one calculation; see lightning/planning/position.py.
    period_position = c.position.at(as_of)
    # Your position follows the period too, as of its end (never past today): the cards then agree with the
    # Net worth chart beside them, which ends there (feedback ticket 80, 2026-10-14).
    position_day = min(as_of, today())
    position = period_position if position_day == as_of else c.position.at(position_day)
    cash_accounts = [
        {"id": account.id, "label": account.label,
         "value": c.reporting.owned_account_value(account.id, position_day),
         "type": _ACCOUNT_TYPE_LABELS[account.account_type]}
        for account in accounts if account.account_type in {AccountType.CASH, AccountType.BANK}
    ]
    cash_accounts.extend({**row, "type": "Brokerage cash"}
                         for row in c.reporting.owned_brokerage_cash_by_account(position_day))
    owe = position.owe
    read_phone_sms(request, c)  # new bank messages join the review before Needs you is counted
    # One review inbox: every decision waiting on the user (lightning/workflows/review.py).
    inbox = ReviewInbox(c)
    attention = inbox.items(today())
    attention_groups = grouped(attention)
    setup = _setup_steps(c, accounts)
    change, change_reason = c.position.change_in_what_you_own(first, as_of, since_first_record=period.key == "all")
    cash_flow = c.reporting.cash_flow(first, as_of)
    closing_report = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(first), fmt_date(as_of))
    opening_report = closing_report["opening"]
    period_result = closing_report["result"]
    holdings_value = closing_report["value"]
    investment_cash = closing_report["investment_cash"]
    portfolio_value = holdings_value   # owner decision 2026-10-04: brokerage cash is not portfolio
    investment_report = {
        "holdings_value": holdings_value, "brokerage_cash": investment_cash,
        "portfolio_value": portfolio_value, "new_money": closing_report["net_money"],
        "income_collected": closing_report["dividends"],
        "period_result": period_result, "period_result_available": period_result is not None,
        "missing": closing_report["missing"] + opening_report["missing"],
        "at_cost": closing_report["at_cost"],
        "holdings_count": sum(1 for row in closing_report["holdings"] if row["price_source"] != "CASH"),
    }
    networth_trend = visuals.net_worth_trend(c, as_of)
    stats = _period_stats(c, period, first, as_of, period_position, cash_flow, change, change_reason,
                          closing_report["net_money"], networth_trend, urlencode(request.query_params))
    # Answer first (guideline 3.33, A09): the change in net worth is the Lead's comparison, not a card of its own;
    # Safe to spend takes its place in the row while the position is today's.
    change_tile = stats.pop(0)
    current = as_of >= today()
    lead_change = page_status.change(change_tile["value"], period.key, current)
    if position_is_today := position_day == today():
        stats.insert(len(stats) - 1, _safe_tile(inbox.forecast))  # the phone's tiles (C06.1)
    # The PC's row is A08 cards, each against something: the savings rate against your usual one, the investing
    # rate against the period before, Safe to spend against free cash, Left in plan against the plan.
    if period.key == "month":
        before_to = first - timedelta(days=1)
        before_from, before_label = before_to.replace(day=1), month_of(before_to)
    else:
        before_to = first - timedelta(days=1)
        before_from, before_label = before_to - (as_of - first), "the period before"
    flow_before = c.reporting.cash_flow(before_from, before_to)
    added_before = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(before_from), fmt_date(before_to))["net_money"]
    plan_month = month_of(as_of)
    kpi_cards = kpis.overview(
        cash_flow, period_chip=_period_chip(period, first, as_of), rates=visuals.savings_rates(c, as_of),
        usual=c.reporting.usual_savings_rate(as_of), invest=investing_rate(closing_report["net_money"], cash_flow.net),
        invest_before=investing_rate(added_before, flow_before.net), before_label=before_label,
        money_added=closing_report["net_money"], forecast=inbox.forecast if position_is_today else None,
        plan=c.budgets.plan_summary(plan_month) if c.budgets.has_plan(plan_month) else None, month=plan_month,
        savings_href="#savings-squares", invest_href=f"/investments?{urlencode(request.query_params)}")
    status = page_status.overview(cash_flow.inflows, cash_flow.outflows, cash_flow.net, cash_flow.savings_rate,
                                  cash_flow.rate_says_nothing, period.key, current, bool(accounts))
    dates_note = ("so far" if current and period.key in ("month", "ytd") else "year to date" if period.key == "ytd" else "")
    recent_rows = c.reporting.register_page(None, "1900-01-01", "9999-12-31", 1, 10)[0]  # the phone leads with these (C11.1)
    phone = _phone_overview(position, inbox.forecast, attention_groups, lead_change) if getattr(request.state, "phone", False) and position_is_today else None
    # The PC shows the flows on Spending (owner, 2026-10-21); the phone keeps them as folded rows (guideline C11.1).
    phone_flows = (visuals.cash_flow_charts(c, first, as_of, period.key == "month", today())
                   if getattr(request.state, "phone", False) else {})
    return render(
        request,
        "dashboard/index.html", **phone_flows,
        stats=stats, recent_rows=recent_rows,
        flow_columns=visuals.cash_flow_columns(c, first, as_of, cash_flow),
        money_in_rows=visuals.money_in_groups(c, first, as_of),
        money_out_rows=visuals.money_out_groups(c, first, as_of),
        wealth_donut=visuals.holdings_donut(position, include_cash=True),
        networth_trend=networth_trend, free_cash_steps=visuals.free_cash_steps(position),
        month=month, this_month=month_of(today()), period=period, period_error=period_error,
        date_from=fmt_date(first), date_to=fmt_date(as_of), as_of=fmt_date(as_of), position_as_of=fmt_date(position_day), position_is_today=position_is_today, status=status, kpi_cards=kpi_cards,
        waffle=saved_and_invested(cash_flow, closing_report["net_money"]), dates_note=dates_note, lead_change=lead_change,
        pos=position, cash_accounts=cash_accounts, owe=owe,
        kept_apart_accounts=c.reporting.owned_cash_kept_apart_by_account(position.as_of),
        attention=attention, attention_groups=attention_groups, setup=setup,
        investment_report=investment_report, cash_flow=cash_flow, phone=phone,
    )


# The welcome page offers Mohab's year and these three stories; Abdelrahman's stays loadable by route.
WELCOME_SAMPLES = ("amr", "menna", "fatma")


@router.post("/setup/currency")
async def set_welcome_currency(request: Request):
    """Register the profile currency and the others held; the base only moves while the profile is empty."""
    c = container(request)
    form = await request.form()
    code = str(form.get("currency", "")).strip().upper()
    extras = []
    for value in form.getlist("extra"):
        value = str(value).strip().upper()
        if value and value != code and value not in extras:
            extras.append(value)
    known = {row["code"] for row in c.currencies.suggestions()}
    if code not in known or any(extra not in known for extra in extras):
        return redirect("/", "Choose the profile currency before adding an account.")
    try:
        if getattr(c, "is_journal", False):
            c.journal_workflows.setup_currencies(code=code, extras=extras, was_empty=not bool(c.accounts.list()))
            return redirect("/", f"Currencies saved: {' · '.join([c.base_currency] + extras)}.")
        if not c.accounts.list():
            c.currencies.register(code)
            c.set_profile_currency(code)
        for extra in extras:
            c.currencies.register(extra)
    except (ValueError, LightningError) as exc:
        message = exc.message if isinstance(exc, LightningError) else str(exc)
        return redirect("/", message)
    c.settings.set("setup_currencies_done", "1")
    return redirect("/", f"Currencies saved: {' · '.join([c.base_currency] + extras)}.")


@router.post("/setup/guide")
async def setup_guide(request: Request):
    form = await request.form()
    action = str(form.get("action", ""))
    if action not in ("dismiss", "show"):
        raise LightningError("Choose whether to show or dismiss the setup guide.")
    container(request).settings.set("setup_guide_dismissed", "1" if action == "dismiss" else "0")
    return redirect("/")


def _salary_form(request, values=None, error="", status_code=200, error_field=""):
    c = container(request)
    accounts = [a for a in c.accounts.list(active_only=True)
                if a.account_type.value in ("BANK", "CASH") and a.currency == c.base_currency]
    values = values or {"account_id": request.query_params.get("account", str(accounts[0].id) if accounts else ""),
                        "amount": "", "payday": ""}
    return render(request, "dashboard/salary_setup.html", values=values, accounts=accounts,
                  error=error, status_code=status_code, error_field=error_field)


@router.get("/setup/salary")
async def salary_setup(request: Request):
    from lightning.planning.domain import PlanKind
    if container(request).planning.items((PlanKind.INCOME,)):
        return redirect("/plan/recurring", "Your income is already set up. Edit it in Recurring.")
    return _salary_form(request)


@router.post("/setup/salary")
async def save_salary_setup(request: Request):
    from lightning.workflows.salary_setup import set_up_salary
    form = await request.form()
    values = {key: str(form.get(key, "")) for key in ("account_id", "amount", "payday")}
    try:
        container(request).salary_setup.set_up_salary(**values)
    except LightningError as exc:
        return _salary_form(request, values, exc.message, 400, exc.field or "")
    return redirect("/plan/recurring", "Salary added. Add your bills when you are ready.")


def _setup_steps(c, accounts) -> list[dict] | None:
    """Get set up: the five things that make the Overview useful, in the order a new user meets them.
    Shown until every step is done or the user dismisses it; completed steps tick themselves."""
    if c.settings.get("setup_guide_dismissed") == "1":
        return None
    from lightning.planning.domain import PlanKind
    bank = next((a for a in accounts if a.account_type.value == "BANK" and a.active), None)
    waiting = c.bank_imports.first_pending_review()
    history = {"label": "Bring in your history", "detail": "Import your bank's statement, or add rows by hand",
               "done": c.reporting.has_income_or_spending() and waiting is None,
               "href": f"/accounts/{bank.id}/import" if bank else "/accounts", "action": "Import a statement"}
    if waiting is not None:   # a statement is half-reviewed: the step is not done until it is posted
        history |= {"detail": f"{waiting['file_name']} is waiting for your review",
                    "href": f"/accounts/{waiting['account_id']}/import/{waiting['batch_id']}", "action": "Finish the import"}
    steps = [
        {"label": "Add where you keep your money", "detail": "Your bank, cash, certificates, THNDR and gold",
         "done": bool(accounts), "href": "/accounts/new", "action": "Add an account"},
        history,
        {"label": "Add your salary and bills", "detail": "So Cash planning knows what comes in and what is due",
         "done": bool(c.planning.items((PlanKind.INCOME,))),
         "href": "/plan/recurring" if c.planning.items((PlanKind.INCOME,)) else "/setup/salary",
         "action": "Add salary and bills"},
        {"label": "Set an emergency fund", "detail": "Cash set aside for the unexpected",
         "done": any(r.get("kind") == "EMERGENCY" and (r.get("allocated") or ZERO) > ZERO for r in c.reserves.list_active()),
         "href": "/plan/reserves", "action": "Set it"},
        {"label": "Make a budget", "detail": "A plan for this month, built from your own spending",
         "done": c.budgets.has_plan(month_of(today())), "href": "/budget", "action": "Make a budget"},
    ]
    return None if all(step["done"] for step in steps) else steps


def _period_stats(c, period, first, as_of, position, cash_flow, change, change_reason, money_added,
                  networth_trend, period_query) -> list[dict]:
    """The Overview's four stat cards: change in net worth, savings rate, investing rate and left in plan.

    Every number is a figure from lightning.core.figures; the cards only choose words and tones."""
    sign = lambda v: "up" if v is not None and v > 0 else "down" if v is not None and v < 0 else "flat"
    period_name = {"month": month_of(first), "ytd": "Year to date", "all": "All time"}.get(
        period.key, f"{fmt_date(first)} to {fmt_date(as_of)}")
    owes = position.what_you_owe > 0
    if owes:
        nw_change, nw_reason = c.position.change_in_net_worth(first, as_of, since_first_record=period.key == "all")
    else:
        nw_change, nw_reason = change, change_reason
    lead = "net_worth" if owes else "what_you_own"
    stats = [{
        "key": "change", "surface": "hold", "label": label("change_in_net_worth" if owes else "change_in_what_you_own"),
        "value": nw_change, "kind": "money", "badge": {"tone": "flat" if as_of.day < calendar.monthrange(as_of.year, as_of.month)[1] else sign(nw_change), "text": period_name + (" so far" if as_of.day < calendar.monthrange(as_of.year, as_of.month)[1] else "")},
        "sub": nw_reason if nw_change is None else f"{label(lead)} {fmt(position.net_worth if owes else position.what_you_own)}",
        "spark": visuals.trend_spark(networth_trend), "spark_tone": "hold", "href": "#owned-heading",
    }]
    rate = cash_flow.savings_rate
    # Honest numbers: when money out is more than twice money in, a rate like −1,375% says nothing.
    # Show the gap in words instead (guideline A01); Financial health does the same.
    thin = cash_flow.rate_says_nothing
    if rate is None:
        savings_sub = "No money in this period"
    elif thin:
        savings_sub = f"{fmt(-cash_flow.net)} more went out than the {fmt(cash_flow.inflows)} that came in"
    else:
        savings_sub = f"kept of {fmt(cash_flow.inflows)} {label('money_in').lower()}"
    # Feedback ticket 97: spending more than came in is not a negative savings rate. The card says so, in rose.
    overspent = rate is not None and not thin and cash_flow.net < 0
    if overspent:
        savings_sub = f"{fmt(-cash_flow.net)} more went out than the {fmt(cash_flow.inflows)} that came in"
    stats.append({
        "key": "savings", "surface": "over" if thin or overspent else "in",
        "label": "Spent over money in" if overspent else label("savings_rate"),
        "value": -rate if overspent else None if thin else rate, "kind": "rate", "empty": "—" if thin else None,
        "badge": {"tone": sign(cash_flow.net), "text": period_name + (" so far" if as_of.day < calendar.monthrange(as_of.year, as_of.month)[1] else "")},
        "figure": cash_flow.net, "sub": savings_sub,
        "spark": visuals.savings_rate_spark(c, as_of), "spark_tone": "in",
        "href": "#savings-squares",  # the waffle lives behind the Savings rate (owner, 2026-10-19)
    })
    invest = investing_rate(money_added, cash_flow.net)
    stats.append({
        "key": "investing", "surface": "in", "label": label("investing_rate"), "value": invest, "kind": "rate",
        "badge": {"tone": sign(money_added), "text": period_name + (" so far" if as_of.day < calendar.monthrange(as_of.year, as_of.month)[1] else "")},
        "figure": money_added, "sub": label("new_money_in").lower() if invest is not None else "Nothing kept this period",
        "meter": {"width": float(max(min(invest, 100), 0)) if invest is not None else 0.0, "tone": "hold"},
        "href": f"/investments?{period_query}",
    })
    month = month_of(as_of)
    if c.budgets.has_plan(month):
        summary = c.budgets.plan_summary(month)  # the same figures as the Budget tab
        planned, left = summary["planned"], summary["left"]
        used = planned - left
        share = used / planned * 100 if planned > 0 else None
        stats.append({
            "key": "plan", "surface": "over" if left < 0 else "out",
            "label": f"Over plan · {month}" if left < 0 else f"{label('left_in_plan')} · {month}",
            "value": -left if left < 0 else left, "kind": "money",
            "badge": {"tone": "over" if left < 0 else "flat",
                      "text": "Over plan" if left < 0 else (f"{share:.0f}% used" if share is not None else month)},
            "sub": f"of {fmt(planned)} {label('planned').lower()}",
            "meter": {"width": float(min(max(share or 0, 0), 100)), "tone": "over" if left < 0 else "in"},
            "href": f"/budget?month={month}", "warn": keynotes.low_confidence_note(summary["low_confidence"]),
        })
    else:
        stats.append({"key": "plan", "surface": "out", "label": f"{label('left_in_plan')} · {month}", "value": None,
                      "kind": "money", "empty": "No plan yet", "sub": f"Set a plan for {month}",
                      "href": f"/budget?month={month}"})
    return stats


# Needs you on the phone says what is inside in a few words (phone overhaul 2026-10-22): "2 bills · 4 to sort out".
_NEEDS_SHORT = {"payments": ("1 bill", "{n} bills"), "activity": ("1 to sort out", "{n} to sort out"),
                "budget": ("1 on the budget", "{n} on the budget"), "cash": ("1 on cash", "{n} on cash"),
                "prices": ("1 price", "{n} prices"), "other": ("1 other", "{n} others")}


def _safe_hero(f) -> dict:
    """Safe to spend as the phone's hero (phone overhaul 2026-10-22: "can I spend today?"), with its one sentence:
    about how much a day until payday. ``f`` is today's forecast; the figure's home stays Cash planning."""
    value, until = f.safe_to_spend, f.next_income_date
    days = (parse_date(until) - today()).days if until else 0
    if value < 0:
        line = page_status.sentence("{amt} more is promised than your free cash.", amt=fmt(-value))
    elif until and days > 0:
        line = page_status.sentence("About {amt} a day until payday on {sa}.", amt=fmt(value / days), sa=until)
    else:
        line = page_status.sentence("From free cash, after what is promised over the next 3 months.")
    return {"value": value, "line": line, "until": until or ""}


def _phone_overview(position, forecast, groups, lead_change) -> dict:
    """What the phone's Overview adds to the PC's figures: the Safe to spend hero, a Net worth tile, and the words
    on the Needs you card."""
    owes = position.what_you_owe > 0
    worth = {"key": "networth", "surface": "hold", "label": label("net_worth" if owes else "what_you_own"),
             "value": position.net_worth if owes else position.what_you_own, "kind": "money",
             "badge": {"tone": "flat", "text": "Today"},
             "sub": f"{lead_change['figure']} {lead_change['text']}" if lead_change else "",
             "href": "/accounts"}
    parts = []
    for group in groups[:3]:
        one, many = _NEEDS_SHORT.get(group["key"], _NEEDS_SHORT["other"])
        parts.append(page_status.sentence(one if group["count"] == 1 else many, n=group["count"]))
    return {"safe": _safe_hero(forecast), "worth": worth, "needs": parts}


@router.get("/more")
async def more(request: Request):
    """The phone's More tab (phone overhaul 2026-10-22): every section without a slot of its own, each with its live
    figure, the weekly review as a card, then settings as a grouped list. The PC has its sidebar instead."""
    if not getattr(request.state, "phone", False):
        return redirect("/")
    c = container(request)
    day = today()
    position = c.position.at(day)
    inbox = ReviewInbox(c)
    items = inbox.items(day)
    parts = dict(inbox.forecast.safe_to_spend_parts)
    due = -parts.get(label("payments_before_next_income"), ZERO)
    health = c.health.overview(day)
    judged = [item for item in health["figures"] if item.status in ("within your limit", "outside your limit")]
    within = sum(1 for item in judged if item.status == "within your limit")
    first = day.replace(day=1)
    spent = c.reporting.cash_flow(first, day).outflows
    return render(request, "more.html", due=due, until=inbox.forecast.next_income_date or "",
                  portfolio=position.portfolio_value, in_accounts=position.in_your_accounts,
                  within=within, judged=len(judged), spent=spent, month=month_of(day), waiting=len(items),
                  last_review=(c.settings.get("weekly_review_at") or "")[:10], zakat=c.zakat.enabled())
def _period_chip(period, first, as_of) -> str:
    """The period, short, as every card's chip names it."""
    partial = as_of.day < calendar.monthrange(as_of.year, as_of.month)[1]
    return {"month": month_of(first) + (" so far" if partial else ""), "ytd": "Year to date",
            "all": "All time"}.get(period.key, f"{fmt_date(first)} to {fmt_date(as_of)}")


def _safe_tile(f) -> dict:
    """Safe to spend on the Overview: the Cash planning figure (its home), as a card that opens it. ``f`` is today's
    forecast, the one Needs you already worked out."""
    until = f.next_income_date
    share = f"{f.safe_to_spend / f.free_cash * 100:.0f}% of your {fmt(f.free_cash)} free cash" if f.free_cash > 0 else "No free cash today"
    return {"key": "safe", "surface": "over" if f.safe_to_spend < 0 else "hold", "label": label("safe_to_spend"),
            "value": f.safe_to_spend, "kind": "money",
            "badge": {"tone": "over" if f.safe_to_spend < 0 else "flat", "text": f"until {until}" if until else "3 months"},
            "sub": share, "href": "/plan"}


@router.post("/demo")
async def add_demo_household(request: Request):
    """Fill an empty Lightning with the sample household (only while nothing has been added yet)."""
    c = container(request)
    if c.accounts.list():
        return redirect("/", "The sample household can only be added to an empty Lightning.")
    from lightning.demo import build_demo
    try:
        summary = build_demo(c)
    except (LightningError, ValueError) as exc:  # nothing is kept: the ledger part is one transaction
        return redirect("/", f"The sample household could not be added: {getattr(exc, 'message', exc)}")
    return redirect("/", f"Sample household added: Mohab's money from {summary['from']} to {summary['to']}.")


@router.post("/sample/mohab-2026")
async def add_sample_2026(request: Request):
    """Fill an empty Lightning with Mohab's 2026, loaded from the sample CSV files."""
    c = container(request)
    if c.accounts.list():
        return redirect("/", "The 2026 sample can only be added to an empty Lightning.")
    from lightning.samples import load_mohab_2026
    try:
        summary = load_mohab_2026(c)
    except (LightningError, ValueError) as exc:
        return redirect("/", f"The 2026 sample could not be added: {getattr(exc, 'message', exc)}")
    return redirect("/", f"Mohab's 2026 added: {summary['rows']} imported rows across {summary['accounts']} accounts, "
                         f"{summary['from']} to {summary['to']}.")


@router.post("/sample/{story}")
async def add_sample_story(request: Request, story: str):
    c = container(request)
    if c.accounts.list():
        return redirect("/", "A sample story can only be added to an empty Lightning.")
    from lightning.samples.profiles import load_story
    try:
        summary = load_story(c, story)
    except (LightningError, ValueError) as exc:
        return redirect("/", f"The sample story could not be added: {getattr(exc, 'message', exc)}")
    return redirect("/", f"{summary['name']}'s sample added: {summary['rows']} fictional entries, "
                         f"{summary['from']} to {summary['to']}.")


@router.get("/samples/mohab-2026/{name}")
async def sample_file(request: Request, name: str):
    """Download one of the sample CSVs, to try Import CSV with a real file."""
    from fastapi.responses import FileResponse
    from lightning.samples import FILES, MOHAB_2026
    if name not in FILES:
        return redirect("/", "There is no such sample file.")
    return FileResponse(MOHAB_2026 / name, media_type="text/csv; charset=utf-8", filename=name)


@router.get("/explain/{kind}")
async def explain_overview_figure(request: Request, kind: str):
    c = container(request)
    try:
        period = parse_period(request.query_params, today(), c.reporting.first_activity_date())
    except ValidationError:
        period = parse_period({"period": "month", "month": month_of(today())}, today(), c.reporting.first_activity_date())
    day, first = fmt_date(period.end), fmt_date(period.start)
    destination = "/?" + request.url.query
    position = c.position.at(day)
    if kind == "owned":
        title = f"{label('what_you_own')} · known subtotal" if position.unvalued else label("what_you_own")
        figure = "what_you_own"
        explanation = FIGURES["what_you_own"].meaning + " Money and units held for others are left out."
        rows = [{"label": label("cash_you_own"), "value": position.cash_you_own},
                {"label": label("holdings_value"), "value": position.holdings_value}]
        if position.other_you_own:
            rows.append({"label": label("other_you_own"), "value": position.other_you_own})
        total = position.what_you_own
        missing = f" Missing valuation: {'; '.join(position.unvalued)}." if position.unvalued else ""
        change_value, change_reason = c.position.change_in_what_you_own(first, day, since_first_record=period.key == "all")
        change_label = (f"{label('change_in_what_you_own')} since your first record" if period.key == "all"
                        else label("change_in_what_you_own"))
        foot = (f"Position as of {day}. {change_label}: "
                + (fmt(change_value, 0, True) if change_value is not None else f"unavailable · {change_reason}")
                + f". This is wealth movement, not investment return.{missing}")
        action = ("Open Birdview", destination)
    elif kind == "free-cash":
        title = label("free_cash")
        figure = "free_cash"
        explanation = (FIGURES["free_cash"].meaning + " " + FIGURES["bills_due"].meaning
                       + " Brokerage cash counts, but move it to a bank or wallet before everyday spending.")
        rows = [{"label": label("bank_and_wallet_cash"), "value": position.bank_and_wallet_cash},
                {"label": label("brokerage_cash"), "value": position.brokerage_cash}]
        if position.reserves is None:
            total, foot = None, "Free cash is unavailable: reserve history cannot be rebuilt for this date."
        else:
            rows.append({"label": label("reserves"), "value": -position.reserves, "href": "/plan/reserves"})
            if position.bills_due:
                rows.append({"label": label("bills_due"), "value": -position.bills_due, "href": "/plan"})
            total, foot = position.free_cash, f"Position as of {day}."
        action = ("Open Cash planning", "/plan")
    elif kind == "flow":
        title = label("net_flow")
        figure = "net_flow"
        flow = c.reporting.cash_flow(first, day)
        explanation = FIGURES["money_in"].meaning + " " + FIGURES["money_out"].meaning
        rows = [{"label": label("money_in"), "value": flow.inflows}, {"label": label("money_out"), "value": -flow.outflows}]
        total = flow.net
        foot = f"{first} to {day}. This is cash flow, not wealth change or investment return."
        action = ("Open Birdview", destination)
    else:
        return render(request, "not_found.html", status_code=404, message="Explanation not found.")
    return render(request, "dashboard/explanation.html", title=title, explanation=explanation, figure=figure,
                  rows=rows, total=total, foot=foot, recent=[], action=action)


@router.get("/needs-you/{key}")
async def needs_you_group(request: Request, key: str):
    """One group of Needs you (feedback ticket 84): its decisions, each with the action that settles it."""
    c = container(request)
    items = [item for item in ReviewInbox(c).items(today()) if group_of(item) == key]
    return render(request, "needs_you.html", label=GROUP_LABELS.get(key, "Other"), items=items)


@router.get("/money-from-others")
async def money_from_others(request: Request):
    c = container(request)
    owners = c.reporting.money_from_others_by_owner(today())
    investments = c.reporting.money_from_others_investments(today())
    held_total = c.position.at(today()).held_for_others
    return render(request, "money_from_others.html", accounts=c.accounts.list(active_only=True),
                  counterparties=c.counterparties.list_active(), held_total=held_total,
                  owners=owners, investments=investments,
                  entries=c.reporting.money_from_others_history(),
                  investment_entries=c.money_from_others.investment_history())


@router.post("/money-from-others")
async def add_money_from_others(request: Request):
    c = container(request)
    form = await request.form()
    try:
        owner_text = str(form.get("owner", "")).strip()
        party = c.counterparties.resolve(owner_text)
        if not party or not party["active"]:
            raise ValidationError("Choose an active saved Counterparty as Whom.", "owner")
        owner = party["name"]
        account = c.accounts.require_usable(int(form.get("account_id", "0")))
        amount = to_decimal(form.get("amount", ""))
        if amount == 0:
            raise ValidationError("Use a positive amount for money received and a negative amount when it is returned.", "amount")
        day = parse_date(form.get("date", today().isoformat())).isoformat()
        c.money_from_others.record(day, owner, account.id, amount, str(form.get("notes", "")))
    except (ValueError, ValidationError, InvalidOperation) as exc:
        message = exc.message if isinstance(exc, ValidationError) else "Check the amount, date, and account."
        return redirect("/money-from-others", message)
    return redirect("/money-from-others", "Money-from-others entry saved; your net worth has been adjusted.")
