from __future__ import annotations

from decimal import Decimal
from dataclasses import replace
from datetime import date, timedelta

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, parse_date, parse_month, today
from lightning.core.errors import LightningError, NotFoundError, ValidationError
from lightning.core.refs import DocType
from lightning.core.money import ZERO, fmt, from_e6, signed_pct, to_decimal

from urllib.parse import urlencode

from ..web import container, redirect, render, ui_locale, settled_save
from ..i18n import translate
from ...investments import benchmark as risk_free, events, owned, views as holding_views
from ...assets.catalog import instruments
from ..periods import parse_period
from ...investments.report import (PLANNER_MODES, explain_period, build_investment_report, investment_period, reconcile_portfolio,
                                    saved_and_invested,
                                    period_growth, results_by_asset, suggest_contributions, suggest_by_current_mix,
                                    normalized_target_weights)
from .. import charts, kpis, status as page_status
from lightning.core.figures import label
from lightning.core.plural import counted
from lightning.market.packs import chosen, read_zip
from lightning.market.update import DEFAULT_URL, update_packs
from lightning.workflows import live_prices
from lightning.workflows.market_prices import (fill_followed, followed_packs, forget, held_packs, local_folder,
                                              pack_files, pack_rows)

from .. import keynotes, visuals

router = APIRouter(prefix="/investments")


@router.get("/report-detail")
async def investment_report_detail(request: Request):
    c = container(request)
    kind = request.query_params.get("kind", "flows")
    start, end = request.query_params.get("from", "1900-01-01"), request.query_params.get("to", fmt_date(today()))
    if kind == "holdings":
        report = build_investment_report(c.db, c.accounts, c.assets, c.reporting, start, end)
        return render(request, "investments/report_detail.html", title="Owned holdings",
                      rows=report["holdings"], holdings=True, show_popup=True)
    rows = c.investments.report_transactions(kind, start, end)
    rows = [dict(row) for row in rows]  # database rows and money-added dicts alike; every row gets its amount
    rows = [row if "amount" in row else
            {**row, "amount": from_e6(row["amount_base_e6"]) if row.get("amount_base_e6") is not None else None}
            for row in rows]
    return render(request, "investments/report_detail.html", title={"dividends": label("dividends_and_interest"), "sales": label("realized_gain"),
                  "flows": label("new_money_in")}.get(kind, "Investment transactions"),
                  rows=rows, show_amount=kind in {"flows", "dividends"}, show_popup=True)


def _allocation_classes(c):
    return sorted({c.assets.display_name(cls.id).split(" › ")[-1] for cls in c.assets.investment_classes()},
                  key=str.casefold)

KINDS = {
    "buy": ("Buy", "Units in, cash out — at cost, fees included."),
    "sell": ("Sell", "Units out, cash in — what you receive after fees."),
    "dividend": ("Dividend", "Cash paid to you by an investment you hold."),
    "return_of_capital": ("Return of capital", "A fund pays part of what you paid in back: cash arrives, your units stay, your cost falls."),
    "bonus_or_split": ("Bonus or split", "Bonus shares, a split or a reverse split: your units change, your cost does not, and no purchase appears."),
    "holding": ("Add a holding you already own", "Units you had when you started tracking, and what you paid in total."),
}
FIELDS = ("date", "account_id", "asset_id", "quantity", "price", "fees", "fees_included", "cash_account_id", "amount", "total_cost", "total",
          "notes", "owner_id", "dividend_basis")


def _int(value) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


@router.get("")
async def portfolio(request: Request):
    c = container(request)
    today_date = today()
    try:
        # All time starts at your first record, as on every other tab.
        period = parse_period(request.query_params, today_date, c.reporting.first_activity_date())
        period_error = ""
    except LightningError as exc:
        period = parse_period({}, today_date)
        period_error = exc.message  # say why this month is shown instead of the range asked for
    day = period.end_text
    investment_report = investment_period(c.db, c.accounts, c.assets, c.reporting,
                                          period.start_text, period.end_text)
    p = c.investments.portfolio(day)
    before_day = fmt_date(period.start.fromordinal(period.start.toordinal()-1))  # not money: dates
    investment_report.update(reconcile_portfolio(c.investments, c.accounts, c.reporting, investment_report,
                                                 period.start_text, period.end_text))
    prior = c.investments.portfolio(before_day)
    targets = c.investments.target_weights()
    allocation_classes=_allocation_classes(c)
    interest_id = next((cat.id for cat in c.categories.tree() if cat.code == "EXP.INVEST.INTEREST"), None)
    period_interest = c.investments.period_interest(interest_id, period.start_text, period.end_text)
    own = owned.owned_portfolio(c.reporting, c.money_from_others, c.assets.all_investment_preferences(), p, prior,
                                day, before_day, period_interest)
    owned_rows, prior_custody = own.owned_rows, own.prior_custody
    position = c.position.at(period.end)
    class_results, _ = results_by_asset(c.investments, c.money_from_others, c.reporting, before_day, day)
    notes = [n for n in (keynotes.best_class([{"label": k, "result": v} for k, v in class_results.items()]),
                         keynotes.at_cost(investment_report.get("at_cost", []))) if n]
    extras = _page_extras(c, period, p, prior, owned_rows, prior_custody, before_day, investment_report)
    extras.update(_view_extras(c, request, extras, investment_report, day))
    # Everything sold in the period: nothing is held, but the period still has a gain or loss to show.
    period_activity = bool(investment_report.get("result") or own.period_realized or own.period_distributions)
    # Answer first (guideline 3.33): Portfolio value is the Lead and the period's net gain or loss its comparison;
    # the allocation sits beside it. The waffle and Biggest holdings left (A09.2: one home per figure).
    result, value, current = extras["hero_result"], extras["hero_value"], period.end >= today_date
    chip_text = {"month": period.start_text[:7], "ytd": "Year to date", "all": "All time"}.get(
        period.key, f"{period.start_text} to {period.end_text}")
    lead = None
    if value is not None and (owned_rows or period_activity):
        compare = (kpis.compare(label("result"), fmt(result, 0, True), "good" if result >= 0 else "bad") if result is not None
                   else kpis.compare("A dated price is missing, so the result is unavailable"))
        ret = p.display_return if not p.has_other_owners else None
        spark, change = extras["value_spark"], extras["hero_change"]
        six = (f"{fmt(change, 0, True)} since six months ago" + (f", excluding {fmt(spark['added'], 0)} you already owned"
                                                                  if spark.get("added") else "")) if change is not None else ""
        since = f"Return since purchase {signed_pct(ret.percent)}%" if ret and ret.percent is not None else ""
        if result is not None and not result and current and change is not None:
            # A08.5 (3Q2): nothing has moved yet this period, so the comparison is the last six months, not a dead 0
            compare = kpis.compare("since six months ago", fmt(change, 0, True), "good" if change >= 0 else "bad")
            six = f"{label('result')} 0" + (f", excluding {fmt(spark['added'], 0)} you already owned"
                                                   if spark.get("added") else "")
        # BT-12AC: the Lead and its parts come from one function over the same holdings, so they add up;
        # what has no cost or market price (a share of a flat) is its own part, not dropped.
        parts = extras["lead_parts"].scaled(extras["lens"]["divisor"])
        value = parts.value
        part_line = " · ".join(text for text in (
            f"Cost {fmt(parts.cost, 0)}" if parts.cost else "",
            f"Unrealized gain {fmt(parts.unrealized, 0, True)}" if parts.cost else "",
            f"Valued by you {fmt(parts.valued_by_you, 0)}" if parts.valued_by_you else "") if text)
        lead = kpis.card(label("portfolio_value"), value, compare, tone="hold", key="value", chip_=kpis.chip(chip_text),
                         visual=kpis.segments([("Cost", parts.cost, "neutral"), ("Unrealized gain", parts.unrealized, "in"),
                                               ("Valued by you", parts.valued_by_you, "hold")]),
                         line_=kpis.line(part_line + (" · " if part_line and (six or since) else "") + (six or since)))  # not money: words; the return since purchase is also the table's All holdings row
    status = page_status.investments(investment_report.get("result"), bool(owned_rows), period.key, current)
    divisor = extras["lens"]["divisor"]   # the USD lens shows the allocation card and brokerage cash in dollars too
    lensed = lambda amount: owned.in_lens(amount, divisor)  # noqa: E731
    allocation = {"what_you_own": lensed(position.what_you_own), "after_sale": lensed(position.holdings_after_sale),
                  "cash": lensed(investment_report.get("investment_cash")),
                  "locked": [{"asset": item.asset, "locked_until": item.locked_until, "value": lensed(item.value)}
                             for item in position.locked_holdings]}
    if divisor != 1:
        extras["biggest"] = {**extras["biggest"], "rows": [{**r, "value": owned.in_lens(r["value"], divisor)} for r in extras["biggest"]["rows"]]}
    return render(request, "investments/index.html", p=p, asset_class_rows=own.asset_class_rows, **extras, lead=lead, status=status,
                  explain=explain_period(investment_report, period.start_text, period.end_text),
                  pos=position, notes=notes, investment_donut=visuals.holdings_donut(position, divisor=divisor), allocation=allocation,
                  accounts=c.investments.investment_accounts(),
                  has_assets=bool(c.assets.investments(active_only=True)), owned_value=own.owned_value,
                  owned_cost=own.owned_cost, owned_unrealized=own.owned_unrealized, custody_units=own.custody,
                  own_by_holding=own.own_by_holding, period=period, period_realized=own.period_realized,
                  period_dividends=own.period_distributions, since_xirr=(p.xirr if not p.has_other_owners else None),
                  since_return=p.display_return if not p.has_other_owners else None,
                  owned_rows=owned_rows, period_activity=period_activity, period_error=period_error,
                  buckets=own.buckets, targets=targets, target_total=owned.target_total(targets),
                  owned_positions=own.owned_positions, max_class_result=own.max_class_result,
                  allocation_classes=allocation_classes, own_units_by_holding=own.own_units_by_holding,
                  starting_owned_value=own.starting_owned_value, period_value_change=own.period_value_change,
                  investment_report=investment_report, base=c.reporting.base_currency)


def _link(request: Request, **changes) -> str:
    """This page's address with some query parameters changed (None drops one); the period and the rest stay."""
    query = {**dict(request.query_params), **changes}
    query = {k: v for k, v in query.items() if v not in (None, "")}
    return "/investments" + ("?" + urlencode(query) if query else "")


def _view_extras(c, request: Request, extras: dict, report: dict, day: str) -> dict:
    """Request choices and links around the investment grouping/lens read model."""
    base = c.reporting.base_currency
    view = holding_views.parse_view(request.query_params.get("view"))
    rate = c.reporting.valuer.fx("USD", day) if base != "USD" else None
    figures = holding_views.grouped_figures(
        extras["holding_groups"], extras["holdings_total"], report, extras["value_spark"],
        accounts={a.id: a for a in c.accounts.list()}, assets={a.id: a for a in c.assets.list_assets()},
        base=base, other=translate("Other", ui_locale()), view=view, rate=rate,
        use_usd=request.query_params.get("lens") == "usd")
    figures["view_links"] = {v: _link(request, view=None if v == "class" else v) for v in holding_views.VIEWS}
    figures["lens"].update(egp_link=_link(request, lens=None), usd_link=_link(request, lens="usd"))
    return figures

def _portfolio_value_spark(c, end: date) -> dict:
    """Portfolio value (holdings only; brokerage cash is cash you own) at each of the last six month ends, up to ``end``.
    Always six months back, whatever period the page shows."""
    values, cursor = [], end.replace(day=1)
    months = []
    for _ in range(6):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)  # not money: dates
    for first in reversed(months):
        _, last = parse_month(first.strftime("%Y-%m"))
        # The Position's figure, as on the Overview: deposits are their own figure, not portfolio.
        values.append(c.position.portfolio_value_at(min(last, end)))
    start = next((i for i, v in enumerate(values) if v), None)
    first = values[start] if start is not None else None
    latest = values[-1] if values else None
    added = change = None
    if first is not None:
        # Holdings recorded as already owned after that month end were not growth (audit 2026-10-05).
        _, since = parse_month(list(reversed(months))[start].strftime("%Y-%m"))
        added = c.reporting.holdings_opened_between(since + timedelta(days=1), end) if since < end else ZERO  # not money: dates
        change = owned.six_month_change(latest, first, added)
    return {"spark": charts.sparkline(values), "values": values, "latest": latest, "first": first,
            "change": change, "added": added}


def _page_extras(c, period, p, prior, owned_rows, prior_custody, before_day, report) -> dict:
    """The Investments page in four parts (guideline 2.7): this period's waffle and result, the fixed
    six-month value line, allocation and biggest holdings, the holdings table grouped by class,
    year-to-date dividends and the period's flows by class."""
    day = period.end_text
    flow = c.reporting.cash_flow(period.start, period.end)
    waffle = saved_and_invested(flow, report["net_money"])
    opening = report.get("recon_opening")
    growth = period_growth(report["result"], opening, report["net_money"])
    spark = _portfolio_value_spark(c, today())
    breakdown = c.position.investment_breakdown(day, owned_rows, report)
    holding_groups, horizons = breakdown.groups, breakdown.horizons
    holdings_total = breakdown.total
    biggest = charts.bars_with_other([{"label": r["name"], "value": r["value"], "note": f"{r['weight']:.1f}% · {g['name']}",
                            "href": f"/accounts/{r['account_id']}"} if r["h"] is None else
                           {"label": r["h"].asset_name, "value": r["value"], "note": f"{r['weight']:.1f}% · {r['h'].asset_class.split(' › ')[-1]}",
                            "href": f"/investments/holding/{r['h'].asset_id}?account={r['h'].account_id}&date={day}&start={period.start_text}"}
                           for g in holding_groups for r in g["rows"] if r["value"]], translate("Other", ui_locale()))
    # Dividends collected this year, per holding (fixed: 1 January to today).
    now = today()
    year_start = fmt_date(date(now.year, 1, 1) - timedelta(days=1))  # not money: dates
    current, before = c.investments.portfolio(fmt_date(now)), c.investments.portfolio(year_start)
    dividends = charts.bars([{"label": name, "value": paid} for name, paid in owned.dividends_since(current, before)], 8)
    # The period's flows: money added and taken out, then how each class's prices moved.
    # Price change per class, the report's own part (what a purchase adds is money in, shown beside, never value
    # gained: r30 N1). Rows are keyed by holding, then folded into the holding's class.
    class_of = {(h.asset_id, h.account_id): h.asset_class.split(" › ")[-1] for h, *_ in owned_rows}
    class_of.update({(x.asset_id, x.account_id): x.asset_class.split(" › ")[-1] for x in prior.positions})
    price_part = next(part for part in explain_period(report, period.start_text, period.end_text)["parts"] if part["key"] == "price")
    by_class = owned.by_class(price_part["rows"], class_of)
    class_changes = sorted(by_class.items(), key=lambda item: -abs(item[1]))
    flow_rows = ([row for row in ({"label": "Money in", "value": report["new_money"], "group": "money"},  # not money: lists joined
                                  {"label": "Money out", "value": -report["withdrawn"], "group": "money"}) if row["value"]]
                 + [{"label": name, "value": change, "group": "class"} for name, change in class_changes if change])
    return {"waffle": waffle,
            "growth": growth, "value_spark": spark, "holding_groups": holding_groups, "biggest": biggest,
            # An Account column only when holdings sit in more than one account.
            "holding_accounts": len({h.account_id for h, *_ in owned_rows}),
            "holdings_total": holdings_total, "ytd_dividends": dividends, "ytd_year": now.year,
            "horizons": horizons, "lead_parts": breakdown.lead,
            "flows": charts.diverging(flow_rows)}


@router.get("/planner")
async def planner_popup(request: Request):
    # The Overview's "Plan to invest" passes its free cash: /investments/planner?amount=208602
    return await _render_planner(request, str(request.query_params.get("amount") or "10000"))


@router.post("/planner")
async def calculate_planner(request: Request):
    form=await request.form()
    c=container(request)
    mode=str(form.get("mode",""))
    with settled_save(request, container(request)):
        if mode in PLANNER_MODES: container(request).settings.set("investment_planner_mode", mode)
        if str(form.get("monthly_goal", "")).strip():
            c.settings.set("investment_monthly_goal", str(to_decimal(str(form.get("monthly_goal")), "monthly_goal")))
    return await _render_planner(request,str(form.get("amount","10000")))


@router.post("/risk-free-rate")
async def save_risk_free_rate(request: Request):
    """Add, replace or remove one dated yearly rate. The history is profile-wide; the form sits on a holding's page."""
    form = await request.form()
    c = container(request)
    back = str(form.get("return_to", ""))
    if not back.startswith("/investments/holding/") or "//" in back or "\\" in back:
        back = "/investments"
    day, percent = str(form.get("day", "")), str(form.get("percent", ""))
    try:
        with settled_save(request, c):
            raw = c.settings.get(risk_free.SETTING_KEY)
            try:
                if form.get("action") == "remove":
                    c.settings.set(risk_free.SETTING_KEY, risk_free.remove_rate(raw, day))
                    message = "Rate removed."
                else:
                    c.settings.set(risk_free.SETTING_KEY, risk_free.set_rate(raw, day, percent))
                    message = "Rate saved."
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
    except LightningError as exc:
        return redirect(back + "#risk-free", exc.message)
    return redirect(back + "#risk-free", message)


def _planner_stack(rows: list[dict], other_label: str) -> list[dict]:
    """Four named suggestions and a neutral remainder; keep the detailed rows unchanged."""
    parts = sorted((r for r in rows if r["suggested"] > ZERO), key=lambda r: -r["suggested"])
    if len(parts) <= 4:
        return [{"label": r["bucket"], "value": r["suggested"], "tone": r["tone"]} for r in parts]
    # An existing Other is already a remainder: include it in the one aggregate, even if large.
    named = [r for r in parts if r["bucket"].casefold() != "other"]
    shown = named[:4]
    rest = named[4:] + [r for r in parts if r["bucket"].casefold() == "other"]  # not money: two lists joined
    return ([{"label": r["bucket"], "value": r["suggested"], "tone": r["tone"]} for r in shown]  # not money: lists joined
            + [{"label": other_label, "value": owned.suggested_total(rest), "tone": "reference"}])


def _planner_phone_groups(rows: list[dict], stack: list[dict]) -> tuple[list[dict], list[dict], Decimal]:
    """Keep every recommendation, with at most four named rows before Other."""
    if len(rows) <= 4:
        return rows, [], ZERO
    names = {part["label"] for part in stack[:4]}
    shown = [row for row in rows if row["bucket"] in names and row["bucket"].casefold() != "other"][:4]
    for row in rows:
        if len(shown) == 4:
            break
        if row not in shown and row["bucket"].casefold() != "other":
            shown.append(row)
    rest = [row for row in rows if row not in shown]
    return shown, rest, owned.suggested_total(rest)


async def _render_planner(request: Request, raw_amount: str="10000"):
    c=container(request); amount=to_decimal(raw_amount,"amount")
    if amount<=ZERO: raise ValidationError("Enter an amount greater than zero.","amount")
    mode=c.settings.get("investment_planner_mode")
    if mode not in PLANNER_MODES: mode="prorata"
    day=fmt_date(today()); portfolio=c.investments.portfolio(day)
    custody={(x["account_id"],x["asset_id"]):Decimal(str(x["units"]))
             for x in c.money_from_others.investment_positions(day)}
    metadata = c.assets.all_investment_preferences()
    values, total = owned.owned_by_bucket(portfolio, custody, metadata)
    targets = c.investments.target_weights()
    planning_targets = normalized_target_weights(targets)
    target_total=owned.target_total(targets)
    by_current_mix = not planning_targets and total > ZERO  # no targets: split by what is held now
    suggestions = (suggest_by_current_mix(dict(values), amount) if by_current_mix
                   else suggest_contributions(dict(values),targets,amount,mode))
    tones={cls.name:charts.class_tone(cls.code) for cls in c.assets.list_classes()}  # each class in its own colour
    rows=[]
    for bucket in sorted(set(values)|set(targets),key=lambda b:(-values.get(b,ZERO),b.casefold())):
        value=values.get(bucket,ZERO); suggested=suggestions.get(bucket,ZERO)
        shares=owned.planner_row(bucket, value, total, suggested, amount)
        rows.append({"bucket":bucket,"value":value,"weight":shares["weight"],
                     "target":planning_targets.get(bucket),"suggested":suggested,"tone":tones.get(bucket,"other"),
                     "after":shares["after"]})
    stack = _planner_stack(rows, translate("Other", ui_locale()))
    phone_shown, phone_other, phone_other_total = _planner_phone_groups(rows, stack)
    return render(request,"investments/planner.html",amount=amount,mode=mode,rows=rows,target_total=target_total,
                  stack=stack, phone_shown=phone_shown, phone_other=phone_other, phone_other_total=phone_other_total,
                  monthly_goal=c.settings.get("investment_monthly_goal") or "",
                  planner_ready=bool(planning_targets) or by_current_mix, by_current_mix=by_current_mix,allocation_sum=owned.suggested_total(rows))


@router.get("/holding/{asset_id:int}")
async def holding_detail(request: Request, asset_id: int):
    c=container(request); day=request.query_params.get("date",fmt_date(today()))
    start=request.query_params.get("start",day)
    portfolio=c.investments.portfolio(day); account_id=_int(request.query_params.get("account"))
    h=next((x for x in portfolio.open if x.asset_id==asset_id and (account_id is None or x.account_id==account_id)),None)
    if h is None: raise NotFoundError("No holding found for that asset and account.")
    h=h.owned_only()
    asset=c.assets.get_asset(asset_id)
    saved_bucket, saved_horizon = c.assets.investment_preferences(asset_id)
    bucket=saved_bucket or h.asset_class.split(" › ")[-1]
    horizon=saved_horizon or "Unassigned"
    before=c.investments.portfolio(fmt_date(parse_date(start).fromordinal(parse_date(start).toordinal()-1)))  # not money: dates
    previous=next((x for x in before.positions if x.asset_id==asset_id and x.account_id==h.account_id),None)
    if previous:
        previous=replace(previous,realized=previous.owned_realized,dividends=previous.owned_dividends,
                         dividend_tax=previous.owned_dividend_tax)
    journey = visuals.holding_journey(c, h.account_id, asset_id, parse_date(day))
    purchases, sales = holding_views.purchase_returns(h, day)
    gain_pct = h.gain_pct
    total_return = h.total_return
    breakdown = charts.waterfall(("What you paid", h.cost_basis),
                                 [("Price change", h.unrealized or ZERO), ("Gain from sales", h.realized),
                                  ("Dividends and interest", h.dividends),
                                  *((("Tax withheld", -h.dividend_tax),) if h.dividend_tax else ())],
                                 ("Value plus what it paid you", h.value_plus_paid))
    stale_price=any(row["asset_id"]==asset_id for row in c.reporting.stale_prices(day))
    rate_history = risk_free.parse_history(c.settings.get(risk_free.SETTING_KEY))
    bench = None if h.has_other_owners else risk_free.benchmark(list(h.flows), h.value, day, rate_history)
    return render(request,"investments/holding.html",rate_history=rate_history,bench=bench,h=h,asset=asset,bucket=bucket,horizon=horizon,day=day,stale_price=stale_price,
                  journey=journey, purchases=purchases, sales=sales, gain_pct=gain_pct, total_return=total_return, breakdown=breakdown,
                  xirr_pct=h.xirr_pct,
                  display_return=h.display_return,
                  start=start,period_realized=h.realized_since(previous),
                  period_dividends=h.dividends_since(previous),
                  allocation_classes=sorted({*_allocation_classes(c), bucket}, key=str.casefold),  # its own bucket is always a choice (5K)
                  show_popup=request.headers.get("X-Lightning-Popup")=="1")


def target_plan(c) -> dict:
    """Owned holdings by allocation class (a holding's own class unless reassigned) against targets."""
    from lightning.investments.report import allocation_plan
    prefs = c.assets.all_investment_preferences()
    rows, _ = c.position.owned_holdings(today())

    def bucket_of(row):
        pref = prefs.get(row.asset_id)
        return (pref["allocation_bucket"] if pref else None) or c.assets.get_class_by_code(row.class_code).name
    values = owned.values_by_bucket(rows, bucket_of)
    return allocation_plan(dict(values), c.investments.target_weights(), _allocation_classes(c))


@router.get("/targets")
async def targets_page(request: Request):
    c = container(request)
    template = "investments/_targets.html" if request.query_params.get("fragment") else "investments/targets.html"
    return render(request, template, plan=target_plan(c), allocation_classes=_allocation_classes(c))


@router.post("/targets")
async def save_target(request: Request):
    c=container(request); form=await request.form(); bucket=str(form.get("bucket","")).strip()
    try:
        allowed = set(_allocation_classes(c)) | {r["name"] for r in target_plan(c)["rows"]}  # every class in the table
        with settled_save(request, container(request)):
            if bucket in allowed and not str(form.get("target_weight", "")).strip():
                c.investments.clear_target_weight(bucket)  # an empty field clears the target
                return Response(status_code=204) if request.headers.get("X-Requested-With") == "fetch" else redirect("/investments/targets", "Target cleared.")
            value=to_decimal(str(form.get("target_weight","")),"target")
            others, left = owned.target_room(c.investments.target_weights(), bucket)
            if value > left:
                room = max(ZERO, left)
                raise LightningError(f"Targets can add up to 100% at most. The others take {others.normalize():f}%, so "
                                     f"{bucket} can be up to {room.normalize():f}%.")
            if bucket not in allowed or value<ZERO or value>100: raise LightningError("Choose an available asset class and a target from 0 to 100.")
            matches=[cls for cls in c.assets.list_classes() if cls.active and c.assets.display_name(cls.id).split(" › ")[-1] == bucket]
            if len(matches)!=1: raise LightningError("This target label is ambiguous. Rename or resolve the asset classes first.")
            cls_id=matches[0].id
            c.investments.set_target_weight(bucket, value, cls_id)
    except LightningError as exc:
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(exc.message, status_code=400, media_type="text/plain")
        return redirect("/investments/targets", exc.message)
    if request.headers.get("X-Requested-With") == "fetch":
        return Response(status_code=204)
    return redirect("/investments/targets", "Target saved.")


@router.post("/asset-plan/{asset_id:int}")
async def save_asset_plan(request: Request,asset_id:int):
    c=container(request); form=await request.form(); asset=c.assets.get_asset(asset_id)
    bucket=str(form.get("allocation_bucket","")).strip() or c.assets.display_name(asset.asset_class_id).split(" › ")[-1]
    if bucket not in _allocation_classes(c): raise LightningError("Choose one of the available investment asset classes.","allocation_bucket")
    horizon=str(form.get("investment_horizon","")).strip()
    if horizon not in ("Short","Medium","Long",""): raise LightningError("Choose Short, Medium, Long, or Unassigned.")
    with settled_save(request, container(request)):
        c.assets.set_investment_preferences(asset_id, bucket, horizon or None)
    back = str(form.get("return_to", "")).strip()
    return redirect(back if back.startswith("/investments") else "/investments", "Horizon saved." if back else "Investment classification saved.")


# -- trades -------------------------------------------------------------------
def _tradable_assets(c, keep: str = ""):
    """What the trade form can take: not a price reference, a certificate or a physical item (each has its own door)."""
    return [a for a in c.assets.investments(active_only=True)
            if str(a.id) == keep or not a.code.startswith(("REF:", "CD:", "OTH:ITEM-"))]


def _cash_accounts(c, keep: str = ""):
    """Where the money comes from or goes to: bank, cash and wallet accounts, never a CD portfolio or gam'eya."""
    return [a for a in c.accounts.list(active_only=True)
            if str(a.id) == keep or a.account_type in (AccountType.BANK, AccountType.CASH, AccountType.CASH_AT_HAND)]


def _form(request: Request, kind: str, values: dict, txn=None, error: LightningError | None = None, status=200):
    c = container(request)
    return render(request, "investments/form.html", status_code=status, kind=kind, title=KINDS[kind][0],
                  spec=events.form_fields(kind) if kind in events.EVENTS else None,
                  hint=KINDS[kind][1], values=values, txn=txn,
                  holding_accounts=c.investments.investment_accounts(), all_accounts=c.accounts.list(active_only=True),
                  assets=_tradable_assets(c, values.get("asset_id", "")),
                  cash_accounts=_cash_accounts(c, values.get("cash_account_id", "")),
                  counterparties=c.counterparties.list_active(), owners=c.counterparties.list_people(),
                  error=error.message if error else "", error_field=(error.field or "") if error else "")


def _save(request: Request, kind: str, v: dict, txn_id: int | None = None):
    c = container(request)
    inv = c.investments
    account, asset, cash = _int(v["account_id"]), _int(v["asset_id"]), _int(v["cash_account_id"])
    owner = _int(v.get("owner_id"))
    if owner:
        party = c.counterparties.get(owner)
        if not party or not party["active"]:
            raise LightningError("Choose an active saved owner.", "owner_id")
    if txn_id:
        txn = inv.update(txn_id, date=v["date"], account_id=account, asset_id=asset, quantity=v["quantity"],
                         price=v["price"], fees=v["fees"], total_fees=v["fees"],
                         fees_included=v.get("fees_included", "1") != "0", total=v["total"], cash_account_id=cash, amount=v["amount"],
                         total_cost=v["total_cost"], notes=v["notes"], owner_id=owner)
    elif kind == "buy":
        if v["total"].strip():
            txn = inv.buy_total(v["date"], account, asset, v["quantity"], v["total"], cash, v["notes"],
                                v["fees"], v.get("fees_included", "1") != "0", owner)
        elif v["price"].strip():
            txn = inv.buy(v["date"], account, asset, v["quantity"], v["price"], v["fees"], cash, v["notes"], owner)
        else:
            txn = inv.buy_total(v["date"], account, asset, v["quantity"], v["total"], cash, v["notes"],
                                v["fees"], v.get("fees_included", "1") != "0", owner)
    elif kind == "sell":
        if v["total"].strip():
            txn = inv.sell_total(v["date"], account, asset, v["quantity"], v["total"], cash, v["notes"],
                                 v["fees"], v.get("fees_included", "1") != "0", owner)
        elif v["price"].strip():
            txn = inv.sell(v["date"], account, asset, v["quantity"], v["price"], v["fees"], cash, v["notes"], owner)
        else:
            txn = inv.sell_total(v["date"], account, asset, v["quantity"], v["total"], cash, v["notes"],
                                 v["fees"], v.get("fees_included", "1") != "0", owner)
    elif kind == "dividend":
        amount = to_decimal(v["amount"], "amount")
        if v.get("dividend_basis", "total") == "per_share":
            units = inv.holding_for_owner(account, asset, v["date"], owner)
            if units <= ZERO:
                raise LightningError("A dividend requires shares held by the selected owner on that date.", "asset_id")
            amount = owned.per_share_total(amount, units)
        txn = inv.dividend(v["date"], account, asset, amount, v["notes"], owner)
    elif kind == "return_of_capital":
        txn = inv.return_of_capital(v["date"], account, asset, v["amount"], cash, v["notes"], owner)
    elif kind == "bonus_or_split":
        txn = inv.bonus_or_split(v["date"], account, asset, v["quantity"], v["notes"], owner)
    else:
        txn = inv.add_holding(account, asset, v["quantity"], v["total_cost"], v["date"] or None,
                              v["notes"], owner)

    return txn


@router.get("/add")
async def add_investment(request: Request):
    """One door (r30 E1-E4): ask what it is, then go to the short form that fits."""
    c = container(request)
    cd = next((a for a in c.accounts.list(active_only=True) if a.account_type == AccountType.DEPOSIT), None)
    return render(request, "investments/add.html",
                  certificate_href=f"/accounts/{cd.id}" if cd else "/accounts/new?type=DEPOSIT")


@router.get("/new")
async def new_trade(request: Request):
    kind = request.query_params.get("kind", "buy")
    kind = kind if kind in KINDS else "buy"
    qp = request.query_params
    values = {k: "" for k in FIELDS}
    values.update(date=fmt_date(today()), account_id=qp.get("account", ""),
                  asset_id=qp.get("asset", ""), dividend_basis="total")
    return _form(request, kind, values)


@router.post("/new")
async def create_trade(request: Request):
    kind = request.query_params.get("kind", "buy")
    kind = kind if kind in KINDS else "buy"
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in FIELDS}
    c = container(request)
    submission = None if getattr(c, "is_journal", False) else str(form.get("submission", ""))
    payload = values | {"kind": kind}
    try:
        with settled_save(request, c):
            txn = c.transactions.submitted(submission, payload)  # a resent form returns its first save (2AD)
            if txn is None:
                txn = _save(request, kind, values)
                c.transactions.remember_submission(submission, payload, txn.id)
    except LightningError as exc:
        return _form(request, kind, values, error=exc, status=400)
    return redirect(f"/accounts/{values['account_id']}" if values["account_id"] else "/investments",
                    f"Saved {txn.ref}.")


@router.get("/{txn_id:int}/edit")
async def edit_trade(request: Request, txn_id: int):
    c = container(request)
    txn = c.transactions.get(txn_id)
    values = {k: "" for k in FIELDS}
    found = c.investments.values_of(txn_id)
    if not found.get("kind") or (txn.type == DocType.OPN and "asset_id" not in found):
        return redirect(f"/transactions/{txn_id}", "This is not an investment transaction.")
    values.update({k: ("" if v is None else str(v)) for k, v in found.items()})
    owner = c.money_from_others.investment_transaction_owner(txn_id)
    party = c.counterparties.resolve(owner) if owner else None
    values["owner_id"] = str(party["id"]) if party else ""
    values["revision"] = c.transactions.revision(txn_id)
    return _form(request, found["kind"], values, txn=txn)


@router.post("/{txn_id:int}/edit")
async def update_trade(request: Request, txn_id: int):
    c = container(request)
    txn = c.transactions.get(txn_id)
    kind = c.investments.values_of(txn_id).get("kind", "buy")
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in FIELDS}
    values["revision"] = form.get("revision")
    try:
        with settled_save(request, c):
            c.transactions.require_revision(txn_id, values["revision"])
            txn = _save(request, kind, values, txn_id=txn_id)
    except LightningError as exc:
        return _form(request, kind, values, txn=txn, error=exc, status=400)
    return redirect("/investments", f"Saved {txn.ref}.")


# -- investments (what you can hold) -------------------------------------------
def _asset_form(request: Request, values: dict, asset=None, error: LightningError | None = None, status=200):
    c = container(request)
    from lightning.market.iso import offered_venues, venue_name
    return render(request, "investments/asset_form.html", status_code=status, values=values, asset=asset,
                  classes=c.assets.investment_classes(), venues=offered_venues(c.base_currency), error=error.message if error else "",
                  error_field=(error.field or "") if error else "",
                  catalogue=[{**row, "exchange": venue_name(row.get("mic"))} for row in instruments()] if asset is None else [])


@router.get("/assets/new")
async def new_asset(request: Request):
    return _asset_form(request, {"class_code": request.query_params.get("class", "STOCK"), "karat": "21",
                                 "name": "", "symbol": "", "isin": "", "mic": "", "notes": ""})


@router.post("/assets/new")
async def create_asset(request: Request):
    c = container(request)
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in ("name", "class_code", "symbol", "karat", "isin", "mic", "notes",
                                                 "currency")}
    try:
        with settled_save(request, container(request)):
            asset = c.assets.create_investment(values["name"], values["class_code"], values["symbol"], values["karat"],
                                               values["isin"], values["notes"], mic=values["mic"],
                                               currency=values["currency"])
    except LightningError as exc:
        return _asset_form(request, values, error=exc, status=400)
    back = request.query_params.get("then", "")
    target = f"/investments/new?kind={back}&asset={asset.id}" if back in KINDS else "/investments"
    return redirect(target, f"Added {asset.name}.")


@router.get("/assets/{asset_id:int}/edit")
async def edit_asset(request: Request, asset_id: int):
    c = container(request)
    asset = c.assets.get_asset(asset_id)
    if asset.is_cash:
        raise NotFoundError("That is a currency, not an investment.")
    values = {"name": asset.name, "class_code": c.assets.get_class(asset.asset_class_id).code, "symbol": asset.ticker,
              "isin": asset.isin or "", "mic": asset.mic or "", "notes": asset.notes, "active": "1" if asset.active else "",
              "fund_page": (asset.market_key or "").removeprefix("EG:FUND:") if (asset.market_key or "").startswith("EG:FUND:") else ""}
    return _asset_form(request, values, asset=asset)


@router.post("/assets/{asset_id:int}/edit")
async def update_asset(request: Request, asset_id: int):
    c = container(request)
    asset = c.assets.get_asset(asset_id)
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in ("name", "class_code", "symbol", "isin", "mic", "notes", "active",
                                                "fund_page")}
    try:
        with settled_save(request, container(request)):
            if "fund_page" in form:
                c.assets.link_fund(asset_id, values["fund_page"])
            asset = c.assets.update_investment(asset_id, values["name"], values["class_code"], values["isin"],
                                               values["notes"], active=bool(values["active"]), ticker=values["symbol"],
                                               mic=values["mic"])
    except LightningError as exc:
        return _asset_form(request, values, asset=asset, error=exc, status=400)
    return redirect("/investments/assets", f"Saved {asset.name}.")


@router.get("/assets")
async def list_assets(request: Request):
    """Financial assets: everything you can hold, with its exchange and ISIN, each one editable."""
    c = container(request)
    classes = {k.id: k for k in c.assets.list_classes()}
    rows = [{"asset": a, "class": classes.get(a.asset_class_id)} for a in c.assets.list_assets()
            if not a.is_cash and not a.code.startswith(("OTH:ITEM-", "REF:"))]  # not physical items or price references
    rows.sort(key=lambda r: (not r["asset"].active, r["class"].sort_order if r["class"] else 99, r["asset"].name.casefold()))
    return render(request, "investments/assets.html", rows=rows)


# -- prices ---------------------------------------------------------------------
@router.get("/prices")
async def prices(request: Request, error: str = ""):
    c = container(request)
    raw_day = request.query_params.get("date")
    try:
        day = fmt_date(parse_date(raw_day)) if raw_day else fmt_date(today())
    except LightningError as exc:
        day, error = fmt_date(today()), exc.message
    portfolio = c.investments.portfolio(day)
    held = {p.asset_id: p for p in portfolio.open}
    rows = []
    for asset in c.assets.investments(active_only=True):
        valuation = c.reporting.value_of(asset.id, 1, day)
        derived = (c.reporting.valuer.reference_price(asset.id, day)  # PR-2: a karat priced from another by purity
                   if valuation.price is None and getattr(asset.exposure, "value", asset.exposure) == "GOLD"
                   and asset.unit == "gram" else None)
        rows.append({"asset": asset, "held": held.get(asset.id),
                     "price": valuation.price if derived is None else owned.exact_from_e6(derived["price_e6"]),
                     "price_date": valuation.price_date if derived is None else derived["date"],
                     "source": valuation.source if derived is None else derived["source"],
                     "is_certificate": c.assets.get_class(asset.asset_class_id).code == "DEPOSIT.CD"})
    rows.sort(key=lambda r: (r["held"] is None, r["asset"].name))
    return render(request, "investments/prices.html", rows=rows, day=day, error=error,
                  pending=c.reevaluations.pending_prices(), market=_followed(c), fails=live_prices.failures(c))


def _followed(c) -> list[dict]:
    """The packs this profile follows, each with what this computer holds of it (or None)."""
    have, rows = pack_files(c.data_dir), {r["id"]: r for r in pack_rows(c.data_dir, ())}
    return [{"id": p, "name": rows.get(p, {}).get("name", p), "source": rows.get(p, {}).get("source", ""),
             "have": have.get(p)} for p in followed_packs(c)]


def _fill_from(c, done: str = "", back: str = "/investments/prices", request: Request | None = None):
    """Fill every held investment's prices from the followed packs, then post the month-end returns they allow."""
    runtime = getattr(getattr(getattr(request, "app", None), "state", None), "profile_session", None)
    runtime = getattr(runtime, "journal", None)
    if runtime is not None:
        if runtime.device.home is None or runtime.automation is None:
            return redirect(back, "Download and apply shared prices on the journal home.")
        from uuid import uuid4
        result = runtime.automation.dispatch_once(
            f"manual-market-fill:{today().isoformat()}:{uuid4().hex}",
            "automation.fill_prices_now", as_of=today().isoformat())
        if result["state"] == "rejected":
            return redirect(back, f"Price update was refused: {result['reason']}")
        if result["state"] not in {"accepted", "accepted-as-existing"}:
            return redirect(back, "Price update saved on this device and is waiting for the journal home.")
        return redirect(back, f"{done} Price update applied on the journal home.".strip())
    try:
        if request is None:
            report = fill_followed(c, today())
        else:
            with settled_save(request, c):
                report = fill_followed(c, today())
        if report is None:
            return redirect(back, f"{done} No price files yet. Download shared prices brings the markets you follow.".strip())
    except LightningError as exc:
        return redirect(back, exc.message)
    return redirect(back, f"{done} {report.summary()}".strip())


async def _update(c, back: str, request: Request | None = None):
    """Download what changed in the followed packs (about 1 MB a month each after the first time), then fill."""
    followed = followed_packs(c)
    try:
        changed, missing = await run_in_threadpool(update_packs, local_folder(c.data_dir), followed,
                                                   c.settings.get("market_url") or DEFAULT_URL)
    except LightningError as exc:
        return redirect(back, exc.message)
    names = {r["id"]: r["name"] for r in pack_rows(c.data_dir, ())}
    done = (f"Updated {', '.join(names.get(p, p) for p, files in changed.items() if files)}."
            if any(changed.values()) else "The price files were already up to date.")
    if missing:
        done += f" Not published yet: {', '.join(names.get(p, p) for p in missing)}."  # not money: words
    return _fill_from(c, done, back, request)


@router.post("/prices/online")
async def online_update(request: Request):
    """Update prices: fetch each held investment's latest close and missing month-ends from the sources.
    The network runs off the request thread; reading and saving stay on it."""
    c = container(request)
    runtime = getattr(getattr(request.app.state, "profile_session", None), "journal", None)
    if runtime is not None:
        if runtime.device.home is None or runtime.automation is None:
            return redirect("/investments/prices", "Fetch online prices from the journal home.")
        on = today()
        if not runtime.automation.start_live_price_fetch(on):
            completed = runtime.automation.poll_live_prices()
            if completed is None:
                return redirect("/investments/prices", "Online price fetching is unavailable or already running on the journal home.")
        return redirect("/investments/prices", "Online price fetch started on the journal home. Results will be applied through the journal.")
    if c.db.read_only:
        return redirect("/investments/prices", "This is a read-only copy; prices cannot be saved here.")
    if not live_prices.enabled():
        return redirect("/investments/prices", "Fetching prices online is off on this computer. Type them, or use a price file.")
    on = today()
    work = live_prices.plan(c, on)
    if not work.wants:
        with settled_save(request, c):
            report = live_prices.save(c, work, {}, [])
        return redirect("/investments/prices", report.summary())
    found, failed = await run_in_threadpool(live_prices.gather, work)
    with settled_save(request, c):
        report = live_prices.save(c, work, found, failed)
    return redirect("/investments/prices", report.summary())


@router.post("/prices/market/fill")
async def market_fill(request: Request):
    return _fill_from(container(request), request=request)


@router.post("/prices/market/update")
async def market_update(request: Request):
    return await _update(container(request), "/investments/prices", request)


@router.post("/prices/market/import")
async def market_import(request: Request):
    """Import a market.zip by hand: one pack, or several as a release ships them. An older pack than the
    one on this computer is skipped; an imported pack you did not follow is followed from now on."""
    c = container(request)
    form = await request.form()
    upload = form.get("file")
    if not upload or not getattr(upload, "filename", ""):
        return redirect("/investments/prices", "Choose a market.zip file.")
    try:
        packs = read_zip(await upload.read())
    except LightningError as exc:
        return redirect("/investments/prices", exc.message)
    have, followed, saved, older = pack_files(c.data_dir), chosen(c.settings.get("market_packs")), [], []
    for pack_id, market in sorted(packs.items()):
        if have.get(pack_id, {}).get("created_at", "") > market.created_at[:10]:
            older.append(pack_id)
            continue
        market.save(local_folder(c.data_dir) / pack_id)  # not money: a path
        saved.append(pack_id)
        if pack_id not in followed:
            followed.append(pack_id)
    with settled_save(request, container(request)):
        c.settings.set("market_packs", ",".join(followed) or "none")
    names = {r["id"]: r["name"] for r in pack_rows(c.data_dir, ())}
    done = f"Imported {', '.join(names.get(p, p) for p in saved)}." if saved else "Nothing was imported."
    if older:
        done += f" Kept your newer {', '.join(names.get(p, p) for p in older)}."  # not money: words
    return _fill_from(c, done, request=request)


@router.get("/prices/markets")
async def price_files(request: Request):
    """Settings › Price files: which exchanges' prices to download and keep."""
    c = container(request)
    return render(request, "investments/price_files.html",
                  rows=pack_rows(c.data_dir, followed_packs(c), held_packs(c)))


@router.get("/prices/online/status")
async def online_status(request: Request):
    """For the corner note while month-end prices are fetched in the background: still running, or what the
    finished fetch saved (saving here, on the database's own thread, as a page render would)."""
    c = container(request)
    note = live_prices.apply_finished(c)
    return JSONResponse({"running": live_prices.running(c), "note": note})


@router.post("/prices/markets/test")
async def test_price_sources(request: Request):
    """Ask each price source once and say what came back, so a failing one is found without guessing."""
    if not live_prices.enabled():
        return redirect("/investments/prices/markets", "Fetching prices online is off on this computer.")
    results = await run_in_threadpool(live_prices.probe)
    return redirect("/investments/prices/markets", live_prices.probe_summary(results))


@router.post("/prices/markets")
async def save_price_files(request: Request):
    c = container(request)
    form = await request.form()
    known = {r["id"] for r in pack_rows(c.data_dir, ())}
    held = held_packs(c)  # a market you hold something on stays followed
    picked = [p for p in form.getlist("pack") if p in known]
    dropped = [p for p in followed_packs(c) if p not in picked and p not in held]
    with settled_save(request, container(request)):
        c.settings.set("market_packs", ",".join(picked) or "none")
    forget(c.data_dir, dropped)
    if form.get("update"):
        return await _update(c, "/investments/prices/markets", request)
    return redirect("/investments/prices/markets", "Saved. Download shared prices on Investment prices brings the markets you added.")


@router.post("/prices/csv")
async def import_price_csv(request: Request):
    """Many prices from one spreadsheet file: Symbol/ISIN/Name, Date (optional), Price (PC roadmap P6)."""
    from lightning.assets.price_csv import read_prices
    c = container(request)
    form = await request.form()
    upload = form.get("file")
    if not upload or not getattr(upload, "filename", ""):
        return redirect("/investments/prices", "Choose a CSV file first.")
    try:
        rows = read_prices(await upload.read(), c.assets.investments(active_only=True), fmt_date(today()))
        with settled_save(request, c):
            for asset_id, day, price in rows.matched:
                c.assets.set_price(asset_id, day, price)
    except (ValueError, LightningError) as exc:
        return redirect("/investments/prices", getattr(exc, "message", str(exc)))
    parts = [f"Saved {len(rows.matched)} price{'' if len(rows.matched) == 1 else 's'}"]  # one part each, " · ", for Arabic
    if rows.unmatched:
        parts.append(f"Not found: {', '.join(rows.unmatched[:5])}{'…' if len(rows.unmatched) > 5 else ''}")
    if rows.bad:
        parts.append(f"Skipped {counted(len(rows.bad), 'row', 'rows')} with no usable price or date")
    note = " · ".join(parts)
    return redirect("/investments/prices", note)


@router.post("/prices")
async def save_prices(request: Request):
    c = container(request)
    form = await request.form()
    day = fmt_date(parse_date(str(form.get("date", "")) or fmt_date(today())))
    values = {int(k[2:]): str(v) for k, v in form.items() if k.startswith("p_") and k[2:].isdigit() and str(v).strip()}
    try:
        portfolio = c.investments.portfolio(day)
        held = {position.asset_id: position for position in portfolio.open}
        for key, raw in form.items():
            if not key.startswith("value_") or not key[6:].isdigit() or not str(raw).strip():
                continue
            asset_id = int(key[6:])
            position = held.get(asset_id)
            if not position or position.quantity <= ZERO:
                raise LightningError("A total value needs a positive holding quantity.", "value")
            if asset_id in values:
                raise LightningError("Enter either a unit price or total value for each investment, not both.", "price")
            values[asset_id] = owned.unit_price(to_decimal(str(raw), "value"), position.quantity)
        with settled_save(request, container(request)):
            count = c.assets.set_prices(day, values)
            for key, raw in form.items():
                if not key.startswith("rp_") or not str(raw).strip():
                    continue
                asset_text, checkpoint = key[3:].split("_", 1)
                c.reevaluations.record_manual_price(int(asset_text), checkpoint,
                                                    to_decimal(str(raw), "price"))
                count += 1  # not money: a count
            c.reevaluations.process_due()
    except LightningError as exc:
        return redirect(f"/investments/prices?date={day}", exc.message)
    return redirect("/investments", f"Saved {counted(count, 'price input', 'price inputs')}; reevaluation catch-up completed." if count
                    else "No prices entered.")


@router.get("/reevaluations")
async def reevaluations_page(request: Request):
    c = container(request)
    return render(request, "investments/reevaluations.html", rows=c.reevaluations.history(),
                  pending=c.reevaluations.pending_prices())
