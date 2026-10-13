from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import replace
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, parse_date, parse_month, today
from lightning.core.errors import LightningError, NotFoundError
from lightning.core.refs import DocType
from lightning.core.money import ZERO, from_e6, to_decimal

from ..web import container, redirect, render
from ...assets.catalog import instruments
from ..periods import parse_period
from ...investments.report import (PLANNER_MODES, build_investment_report, investing_rate, investment_period, saved_and_invested,
                                    period_growth, results_by_asset, suggest_contributions, normalized_target_weights)
from .. import charts
from lightning.core.figures import label
from lightning.market.packs import chosen, read_zip
from lightning.market.update import DEFAULT_URL, update_packs
from lightning.workflows import live_prices
from lightning.workflows.market_prices import fill_followed, forget, local_folder, pack_files, pack_rows

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
    if kind == "dividends":
        rows = [{**row, "amount": from_e6(row["amount_base_e6"])} for row in rows]
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
    opening_report = investment_report["opening"]
    p = c.investments.portfolio(day)
    before_day = fmt_date(period.start.fromordinal(period.start.toordinal()-1))
    invest_ids = [a.id for a in c.investments.investment_accounts()] + [
        a.id for a in c.accounts.list(active_only=True) if a.account_type == AccountType.DEPOSIT]
    opening_adjustments = c.investments.opening_adjustments(invest_ids, period.start_text, period.end_text)
    investment_report["recon_opening"] = (opening_report["investment_cash"] + opening_report["value"]
                                           if opening_report["value"] is not None and
                                           opening_report["investment_cash"] is not None else None)
    investment_report["recon_closing"] = (investment_report["investment_cash"] + investment_report["value"]
                                            if investment_report["value"] is not None and
                                            investment_report["investment_cash"] is not None else None)
    investment_report["opening_adjustments"] = opening_adjustments
    investment_report["recon_result"] = investment_report["result"]
    investment_report["recon_difference"] = (
        investment_report["recon_closing"] - investment_report["recon_opening"] -
        investment_report["net_money"] - investment_report["recon_result"] - opening_adjustments
        if investment_report["recon_opening"] is not None and investment_report["recon_closing"] is not None and
        investment_report["recon_result"] is not None else None)
    prior = c.investments.portfolio(before_day)
    prior_by_key={(x.account_id,x.asset_id):x for x in prior.positions}
    custody = defaultdict(lambda: ZERO)
    for row in c.money_from_others.investment_positions(day):
        custody[(row["account_id"], row["asset_id"])] += row["units"]
    prior_custody = defaultdict(lambda: ZERO)
    prior_custody_value = ZERO
    for row in c.money_from_others.investment_positions(before_day):
        prior_custody[(row["account_id"], row["asset_id"])] += row["units"]
        valuation = c.reporting.value_of(row["asset_id"], row["units"], before_day)
        if valuation.value is not None:
            prior_custody_value += valuation.value
    starting_owned_value = prior.value - prior_custody_value
    custody_value = custody_cost = Decimal(0)
    own_by_holding = {}
    own_cost_by_holding = {}
    own_units_by_holding = {}
    for holding in p.open:
        units = custody.get((holding.account_id, holding.asset_id), 0)
        if not units:
            continue
        value = c.reporting.value_of(holding.asset_id, units, day).value
        held_value = value or Decimal(0)
        if value is not None:
            custody_value += value
        if holding.quantity:
            custody_cost += holding.cost_basis - holding.owned_cost_basis
        own_by_holding[f"{holding.account_id}:{holding.asset_id}"] = (holding.value or Decimal(0)) - held_value
        own_cost_by_holding[f"{holding.account_id}:{holding.asset_id}"] = holding.owned_cost_basis
        own_units_by_holding[f"{holding.account_id}:{holding.asset_id}"] = holding.quantity-units
    owned_value = p.value - custody_value
    owned_cost = p.cost_basis - custody_cost
    owned_unrealized = owned_value - owned_cost
    owned_positions = [h for h in p.open
                       if own_units_by_holding.get(f"{h.account_id}:{h.asset_id}", h.quantity) > ZERO]
    class_totals = defaultdict(lambda: {"total": ZERO, "yours": ZERO, "others": ZERO, "capital": ZERO,
                                        "starting_capital": ZERO, "unrealized": ZERO, "period_unrealized": ZERO,
                                        "realized": ZERO, "dividends": ZERO})
    for holding in p.open:
        category = holding.asset_class.split(" › ")[-1]
        total = holding.value or ZERO
        yours = own_by_holding.get(f"{holding.account_id}:{holding.asset_id}", total)
        row = class_totals[category]
        row["total"] += total; row["yours"] += yours; row["others"] += total-yours
        key = (holding.account_id, holding.asset_id)
        holding_key = f"{holding.account_id}:{holding.asset_id}"
        owned_capital = own_cost_by_holding.get(holding_key, holding.cost_basis)
        row["capital"] += owned_capital
        row["unrealized"] += yours - owned_capital
        old = prior_by_key.get(key)
        old_owned_value, old_owned_capital = ZERO, ZERO
        if old and old.quantity:
            old_other_units = prior_custody.get(key, ZERO)
            old_valuation = c.reporting.value_of(holding.asset_id, old_other_units, before_day)
            old_owned_value = (old.value or ZERO) - (old_valuation.value or ZERO)
            old_owned_capital = old.owned_cost_basis
        row["starting_capital"] += old_owned_capital
        row["period_unrealized"] += (yours - owned_capital) - (old_owned_value - old_owned_capital)
        if total:
            share = yours/total
            row["realized"] += (holding.realized-(old.realized if old else ZERO))*share
            row["dividends"] += (holding.dividends-(old.dividends if old else ZERO))*share
    asset_class_rows = sorted(((name, row) for name, row in class_totals.items() if row["yours"] > ZERO),
                              key=lambda item: (-item[1]["yours"], item[0].casefold()))
    assets = c.assets.all_investment_preferences()
    buckets = defaultdict(lambda: ZERO)
    owned_rows=[]
    for h in p.open:
        key=f"{h.account_id}:{h.asset_id}"
        owned_units = own_units_by_holding.get(key, h.quantity)
        if owned_units <= ZERO: continue
        yours = own_by_holding.get(key, h.value) if h.value is not None else None
        asset=assets.get(h.asset_id)
        bucket=(asset["allocation_bucket"] if asset else None) or h.asset_class.split(" › ")[-1]
        class_text=h.asset_class.casefold()
        horizon=(asset["investment_horizon"] if asset else None) or "Unassigned"
        if yours is not None:
            buckets[bucket]+=yours
        capital=own_cost_by_holding.get(key,h.cost_basis)
        owned_rows.append((h,yours,bucket,horizon,capital,yours-capital if yours is not None else None,
                           owned_units))
    targets = c.investments.target_weights()
    allocation_classes=_allocation_classes(c)
    max_class_result=max((abs(row["period_unrealized"]+row["realized"]+row["dividends"])
                          for _,row in asset_class_rows),default=ZERO) or Decimal(1)
    target_total=sum(targets.values(),ZERO)
    interest_id = next((cat.id for cat in c.categories.tree() if cat.code == "EXP.INVEST.INTEREST"), None)
    period_interest = c.investments.period_interest(interest_id, period.start_text, period.end_text)
    period_distributions = p.dividends-prior.dividends+period_interest
    position = c.position.at(period.end)
    class_results, _ = results_by_asset(c.investments, c.money_from_others, c.reporting, before_day, day)
    notes = [n for n in (keynotes.best_class([{"label": k, "result": v} for k, v in class_results.items()]),
                         keynotes.at_cost(investment_report.get("at_cost", []))) if n]
    extras = _page_extras(c, period, p, prior, owned_rows, prior_custody, before_day, investment_report)
    # Everything sold in the period: nothing is held, but the period still has a gain or loss to show.
    period_activity = bool(investment_report.get("result") or p.realized - prior.realized or period_distributions)
    return render(request, "investments/index.html", p=p, asset_class_rows=asset_class_rows, **extras,
                  pos=position, notes=notes, investment_donut=visuals.holdings_donut(position),
                  accounts=c.investments.investment_accounts(),
                  has_assets=bool(c.assets.investments(active_only=True)), owned_value=owned_value,
                  owned_cost=owned_cost, owned_unrealized=owned_unrealized, custody_units=custody,
                  own_by_holding=own_by_holding, period=period, period_realized=p.realized-prior.realized,
                  period_dividends=period_distributions, since_xirr=(p.xirr if not any(custody.values()) else None),
                  owned_rows=owned_rows, period_activity=period_activity, period_error=period_error,
                  buckets=buckets, targets=targets, target_total=target_total,
                  owned_positions=owned_positions, max_class_result=max_class_result,
                  allocation_classes=allocation_classes, own_units_by_holding=own_units_by_holding,
                  starting_owned_value=starting_owned_value, period_value_change=owned_value-starting_owned_value,
                  investment_report=investment_report, base=c.reporting.base_currency)


def _owned_split(split, units, quantity, gain) -> dict:
    """Your share of a foreign holding's price part and FX part; the FX part takes the rounding so the two add to
    the gain shown."""
    if split is None or gain is None or not quantity:
        return {}
    share = units / quantity
    price_part = (split[0] * share).quantize(Decimal("0.01"))
    return {"price_part": price_part, "fx_part": gain - price_part}


def _portfolio_value_spark(c, end: date) -> dict:
    """Portfolio value (holdings only; brokerage cash is cash you own) at each of the last six month ends, up to ``end``.
    Always six months back, whatever period the page shows."""
    values, cursor = [], end.replace(day=1)
    months = []
    for _ in range(6):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
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
        added = c.reporting.holdings_opened_between(since + timedelta(days=1), end) if since < end else ZERO
        change = latest - first - added
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
    # Assets known only by their balance (a share of a flat, cash left in an older deposit account) are
    # holdings too (owner decision 2026-10-04): the table lists every part of Holdings value.
    traded = {(h.account_id, h.asset_id) for h, *_ in owned_rows}
    balances = [(cls.name, item) for cls in c.position.at(day).classes for item in cls.items
                if (item.account_id, item.asset_id) not in traded and item.value]
    holdings_total = (sum((yours or ZERO for _, yours, *_ in owned_rows), ZERO)
                      + sum((item.value for _, item in balances), ZERO))
    # A balance-only asset has no horizon of its own yet: it is Unassigned, so the horizon split adds up
    # to Holdings value (audit 2026-10-05 #13: the flat was left out).
    horizons = defaultdict(lambda: ZERO)
    for _, yours, _, horizon, *_ in owned_rows:
        horizons[horizon] += yours or ZERO
    for _, item in balances:
        horizons["Unassigned"] += item.value
    # A holding in another currency: its gain from the price and from the exchange rate (Overview #16).
    splits = {(r["account_id"], r["asset_id"]): (r["price_part"], r["fx_part"]) for r in report.get("holdings", [])
              if r.get("price_part") is not None and "account_id" in r}
    groups: dict[str, dict] = {}
    for h, yours, bucket, horizon, capital, unrealized, units in owned_rows:
        name = h.asset_class.split(" › ")[-1]
        g = groups.setdefault(name, {"name": name, "value": ZERO, "cost": ZERO, "rows": []})
        g["value"] += yours or ZERO
        g["cost"] += capital
        g["rows"].append({"h": h, "units": units, "average_cost": capital / units if units else None, "cost": capital,
                          "price": h.price, "value": yours, "gain": unrealized,
                          "gain_pct": unrealized / capital * 100 if unrealized is not None and capital else None,
                          "xirr": h.xirr * 100 if h.xirr is not None and units == h.quantity else None,
                          "horizon": horizon, "weight": (yours or ZERO) / holdings_total * 100 if holdings_total else ZERO,
                          **_owned_split(splits.get((h.account_id, h.asset_id)), units, h.quantity, unrealized)})
    for name, item in balances:
        g = groups.setdefault(name, {"name": name, "value": ZERO, "cost": ZERO, "rows": []})
        g["value"] += item.value
        g["cost"] += item.value
        g["rows"].append({"h": None, "balance": True, "name": item.account, "account_id": item.account_id,
                          "value": item.value, "cost": item.value, "gain": ZERO,
                          "weight": item.value / holdings_total * 100 if holdings_total else ZERO})
    for g in groups.values():
        g["rows"].sort(key=lambda r: (-(r["value"] or ZERO), (r["h"].asset_name if r["h"] else r["name"]).casefold()))
        g["weight"] = g["value"] / holdings_total * 100 if holdings_total else ZERO
        g["gain"] = g["value"] - g["cost"]
        g["gain_pct"] = g["gain"] / g["cost"] * 100 if g["cost"] else None
    holding_groups = sorted(groups.values(), key=lambda g: (-g["value"], g["name"].casefold()))
    biggest = charts.bars([{"label": r["name"], "value": r["value"], "note": f"{r['weight']:.1f}% · {g['name']}",
                            "href": f"/accounts/{r['account_id']}"} if r["h"] is None else
                           {"label": r["h"].asset_name, "value": r["value"], "note": f"{r['weight']:.1f}% · {r['h'].asset_class.split(' › ')[-1]}",
                            "href": f"/investments/holding/{r['h'].asset_id}?account={r['h'].account_id}&date={day}&start={period.start_text}"}
                           for g in holding_groups for r in g["rows"] if r["value"]], 6)
    # Dividends collected this year, per holding (fixed: 1 January to today).
    now = today()
    year_start = fmt_date(date(now.year, 1, 1) - timedelta(days=1))
    current, before = c.investments.portfolio(fmt_date(now)), c.investments.portfolio(year_start)
    paid_before = {(x.account_id, x.asset_id): x.dividends for x in before.positions}
    dividends = charts.bars([{"label": x.asset_name, "value": x.dividends - paid_before.get((x.account_id, x.asset_id), ZERO)}
                             for x in current.positions], 8)
    # The period's flows: money added and taken out, then how each class's value moved.
    start_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for old in prior.positions:
        if not old.quantity or old.value is None:
            continue
        others = prior_custody.get((old.account_id, old.asset_id), ZERO)
        held = c.reporting.value_of(old.asset_id, others, before_day).value if others else ZERO
        start_values[old.asset_class.split(" › ")[-1]] += old.value - (held or ZERO)
    traded_before = {(x.account_id, x.asset_id) for x in prior.positions if x.quantity}
    for cls in c.position.at(before_day).classes:   # balance-only assets, as in the table
        for item in cls.items:
            if (item.account_id, item.asset_id) not in traded_before and item.value:
                start_values[cls.name] += item.value
    # Recording what you already had (an opening balance dated inside the period) is not a change in
    # its value: count it as part of where the period started (audit 2026-10-05 #14).
    openings = c.reporting.opening_by_holding(period.start_text, period.end_text)
    for h, *_ in owned_rows:
        start_values[h.asset_class.split(" › ")[-1]] += openings.get((h.account_id, h.asset_id), ZERO)
    for name, item in balances:
        start_values[name] += openings.get((item.account_id, item.asset_id), ZERO)
    end_values = {g["name"]: g["value"] for g in holding_groups}
    class_changes = sorted(((name, end_values.get(name, ZERO) - start_values.get(name, ZERO))
                            for name in set(start_values) | set(end_values)), key=lambda item: -abs(item[1]))
    flow_rows = ([row for row in ({"label": "Money in", "value": report["new_money"], "group": "money"},
                                  {"label": "Money out", "value": -report["withdrawn"], "group": "money"}) if row["value"]]
                 + [{"label": name, "value": change, "group": "class"} for name, change in class_changes if change])
    return {"waffle": waffle,
            "growth": growth, "value_spark": spark, "holding_groups": holding_groups, "biggest": biggest,
            # An Account column only when holdings sit in more than one account.
            "holding_accounts": len({h.account_id for h, *_ in owned_rows}),
            "holdings_total": holdings_total, "ytd_dividends": dividends, "ytd_year": now.year,
            "horizons": horizons,
            "flows": charts.diverging(flow_rows)}


@router.get("/planner")
async def planner_popup(request: Request):
    return await _render_planner(request)


@router.post("/planner")
async def calculate_planner(request: Request):
    form=await request.form()
    c=container(request)
    mode=str(form.get("mode",""))
    if mode in PLANNER_MODES: container(request).settings.set("investment_planner_mode", mode)
    if str(form.get("monthly_goal", "")).strip():
        c.settings.set("investment_monthly_goal", str(to_decimal(str(form.get("monthly_goal")), "monthly_goal")))
    return await _render_planner(request,str(form.get("amount","10000")))


async def _render_planner(request: Request, raw_amount: str="10000"):
    c=container(request); amount=to_decimal(raw_amount,"amount")
    if amount<=ZERO: raise LightningError("Enter an amount greater than zero.","amount")
    mode=c.settings.get("investment_planner_mode")
    if mode not in PLANNER_MODES: mode="prorata"
    day=fmt_date(today()); portfolio=c.investments.portfolio(day)
    custody={(x["account_id"],x["asset_id"]):Decimal(str(x["units"]))
             for x in c.money_from_others.investment_positions(day)}
    metadata = c.assets.all_investment_preferences()
    values=defaultdict(lambda:ZERO); total=ZERO
    for position in portfolio.open:
        units=max(ZERO,position.quantity-custody.get((position.account_id,position.asset_id),ZERO))
        value=(position.value or ZERO)*units/position.quantity if position.quantity else ZERO
        if value<=ZERO: continue
        meta=metadata.get(position.asset_id)
        bucket=(meta["allocation_bucket"] if meta else None) or position.asset_class.split(" › ")[-1]
        values[bucket]+=value; total+=value
    targets = c.investments.target_weights()
    planning_targets = normalized_target_weights(targets)
    target_total=sum(targets.values(),ZERO)
    suggestions=suggest_contributions(dict(values),targets,amount,mode)
    tones={cls.name:charts.class_tone(cls.code) for cls in c.assets.list_classes()}  # each class in its own colour
    rows=[]
    for bucket in sorted(set(values)|set(targets),key=lambda b:(-values.get(b,ZERO),b.casefold())):
        value=values.get(bucket,ZERO); suggested=suggestions.get(bucket,ZERO)
        rows.append({"bucket":bucket,"value":value,"weight":value/total*100 if total else ZERO,
                     "target":planning_targets.get(bucket),"suggested":suggested,"tone":tones.get(bucket,"other"),
                     "after":(value+suggested)/(total+amount)*100 if total+amount else ZERO})
    return render(request,"investments/planner.html",amount=amount,mode=mode,rows=rows,target_total=target_total,
                  monthly_goal=c.settings.get("investment_monthly_goal") or "",
                  planner_ready=bool(planning_targets),allocation_sum=sum((r["suggested"] for r in rows),ZERO))


@router.get("/holding/{asset_id:int}")
async def holding_detail(request: Request, asset_id: int):
    c=container(request); day=request.query_params.get("date",fmt_date(today()))
    start=request.query_params.get("start",day)
    portfolio=c.investments.portfolio(day); account_id=_int(request.query_params.get("account"))
    h=next((x for x in portfolio.open if x.asset_id==asset_id and (account_id is None or x.account_id==account_id)),None)
    if h is None: raise NotFoundError("No holding found for that asset and account.")
    custody=next((x for x in c.money_from_others.investment_positions(day)
                  if x["account_id"]==h.account_id and x["asset_id"]==asset_id),None)
    if custody and h.quantity:
        own_units=max(ZERO,h.quantity-Decimal(str(custody["units"])))
        factor=own_units/h.quantity
        h=replace(h,quantity=own_units,cost_basis=h.owned_cost_basis,realized=h.owned_realized,
                  dividends=h.dividends*factor,value=(h.value*factor if h.value is not None else None),xirr=None)
    asset=c.assets.get_asset(asset_id)
    saved_bucket, saved_horizon = c.assets.investment_preferences(asset_id)
    bucket=saved_bucket or h.asset_class.split(" › ")[-1]
    horizon=saved_horizon or "Unassigned"
    before=c.investments.portfolio(fmt_date(parse_date(start).fromordinal(parse_date(start).toordinal()-1)))
    previous=next((x for x in before.positions if x.asset_id==asset_id and x.account_id==h.account_id),None)
    journey = visuals.holding_journey(c, h.account_id, asset_id, parse_date(day))
    period_realized = h.realized-(previous.realized if previous else ZERO)
    gain_pct = h.unrealized / h.cost_basis * 100 if h.unrealized is not None and h.cost_basis else None
    total_return = h.total_return
    breakdown = charts.waterfall(("What you paid", h.cost_basis),
                                 [("Price change", h.unrealized or ZERO), ("Gain from sales", h.realized),
                                  ("Dividends and interest", h.dividends)],
                                 ("Value plus what it paid you", h.cost_basis + total_return))
    stale_price=any(row["asset_id"]==asset_id for row in c.reporting.stale_prices(day))
    return render(request,"investments/holding.html",h=h,asset=asset,bucket=bucket,horizon=horizon,day=day,stale_price=stale_price,
                  journey=journey, gain_pct=gain_pct, total_return=total_return, breakdown=breakdown,
                  xirr_pct=h.xirr * 100 if h.xirr is not None else None,
                  start=start,period_realized=h.realized-(previous.realized if previous else ZERO),
                  period_dividends=h.dividends-(previous.dividends if previous else ZERO),
                  allocation_classes=_allocation_classes(c),
                  show_popup=request.headers.get("X-Lightning-Popup")=="1")


def target_plan(c) -> dict:
    """Owned holdings by allocation class (a holding's own class unless reassigned) against targets."""
    from lightning.investments.report import allocation_plan
    prefs = c.assets.all_investment_preferences()
    values = defaultdict(lambda: ZERO)
    rows, _ = c.position.owned_holdings(today())
    for row in rows:
        if row.value is None:
            continue
        pref = prefs.get(row.asset_id)
        bucket = (pref["allocation_bucket"] if pref else None) or c.assets.get_class_by_code(row.class_code).name
        values[bucket] += row.value
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
        if bucket in allowed and not str(form.get("target_weight", "")).strip():
            c.investments.clear_target_weight(bucket)  # an empty field clears the target
            return Response(status_code=204) if request.headers.get("X-Requested-With") == "fetch" else redirect("/investments/targets", "Target cleared.")
        value=to_decimal(str(form.get("target_weight","")),"target")
        others=sum((w for b, w in c.investments.target_weights().items() if b != bucket), ZERO)
        if others + value > 100:
            room = max(ZERO, 100 - others)
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
    c.assets.set_investment_preferences(asset_id, bucket, horizon or None)
    back = str(form.get("return_to", "")).strip()
    return redirect(back if back.startswith("/investments") else "/investments", "Horizon saved." if back else "Investment classification saved.")


# -- trades -------------------------------------------------------------------
def _form(request: Request, kind: str, values: dict, txn=None, error: LightningError | None = None, status=200):
    c = container(request)
    return render(request, "investments/form.html", status_code=status, kind=kind, title=KINDS[kind][0],
                  hint=KINDS[kind][1], values=values, txn=txn,
                  holding_accounts=c.investments.investment_accounts(), all_accounts=c.accounts.list(active_only=True),
                  assets=c.assets.investments(active_only=True),
                  counterparties=c.counterparties.list_active(), owners=c.counterparties.list_owners(),
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
            amount = (amount * units).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        txn = inv.dividend(v["date"], account, asset, amount, v["notes"], owner)
    else:
        txn = inv.add_holding(account, asset, v["quantity"], v["total_cost"], v["date"] or None,
                              v["notes"], owner)

    return txn


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
    try:
        with container(request).db.transaction():
            txn = _save(request, kind, values)
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
    return _form(request, found["kind"], values, txn=txn)


@router.post("/{txn_id:int}/edit")
async def update_trade(request: Request, txn_id: int):
    c = container(request)
    txn = c.transactions.get(txn_id)
    kind = c.investments.values_of(txn_id).get("kind", "buy")
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in FIELDS}
    try:
        with c.db.transaction():
            txn = _save(request, kind, values, txn_id=txn_id)
    except LightningError as exc:
        return _form(request, kind, values, txn=txn, error=exc, status=400)
    return redirect("/investments", f"Saved {txn.ref}.")


# -- investments (what you can hold) -------------------------------------------
def _asset_form(request: Request, values: dict, asset=None, error: LightningError | None = None, status=200):
    c = container(request)
    from lightning.market.iso import VENUES, venue_name
    return render(request, "investments/asset_form.html", status_code=status, values=values, asset=asset,
                  classes=c.assets.investment_classes(), venues=VENUES, error=error.message if error else "",
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
    values = {k: str(form.get(k, "")) for k in ("name", "class_code", "symbol", "karat", "isin", "mic", "notes")}
    try:
        asset = c.assets.create_investment(values["name"], values["class_code"], values["symbol"], values["karat"],
                                           values["isin"], values["notes"], mic=values["mic"])
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
        rows.append({"asset": asset, "held": held.get(asset.id), "price": valuation.price,
                     "price_date": valuation.price_date, "source": valuation.source,
                     "is_certificate": c.assets.get_class(asset.asset_class_id).code == "DEPOSIT.CD"})
    rows.sort(key=lambda r: (r["held"] is None, r["asset"].name))
    return render(request, "investments/prices.html", rows=rows, day=day, error=error,
                  pending=c.reevaluations.pending_prices(), market=_followed(c), fails=live_prices.failures(c))


def _followed(c) -> list[dict]:
    """The packs this profile follows, each with what this computer holds of it (or None)."""
    have, rows = pack_files(c.data_dir), {r["id"]: r for r in pack_rows(c.data_dir, ())}
    return [{"id": p, "name": rows.get(p, {}).get("name", p), "source": rows.get(p, {}).get("source", ""),
             "have": have.get(p)} for p in chosen(c.settings.get("market_packs"))]


def _fill_from(c, done: str = "", back: str = "/investments/prices"):
    """Fill every held investment's prices from the followed packs, then post the month-end returns they allow."""
    try:
        report = fill_followed(c, today())
        if report is None:
            return redirect(back, f"{done} No price files yet. Download shared prices brings the markets you follow.".strip())
    except LightningError as exc:
        return redirect(back, exc.message)
    return redirect(back, f"{done} {report.summary()}".strip())


async def _update(c, back: str):
    """Download what changed in the followed packs (about 1 MB a month each after the first time), then fill."""
    followed = chosen(c.settings.get("market_packs"))
    try:
        changed, missing = await run_in_threadpool(update_packs, local_folder(c.data_dir), followed,
                                                   c.settings.get("market_url") or DEFAULT_URL)
    except LightningError as exc:
        return redirect(back, exc.message)
    names = {r["id"]: r["name"] for r in pack_rows(c.data_dir, ())}
    done = (f"Updated {', '.join(names.get(p, p) for p, files in changed.items() if files)}."
            if any(changed.values()) else "The price files were already up to date.")
    if missing:
        done += f" Not published yet: {', '.join(names.get(p, p) for p in missing)}."
    return _fill_from(c, done, back)


@router.post("/prices/online")
async def online_update(request: Request):
    """Update prices: fetch each held investment's latest close and missing month-ends from the sources.
    The network runs off the request thread; reading and saving stay on it."""
    c = container(request)
    if c.db.read_only:
        return redirect("/investments/prices", "This is a read-only copy; prices cannot be saved here.")
    if not live_prices.enabled():
        return redirect("/investments/prices", "Fetching prices online is off on this computer. Type them, or use a price file.")
    on = today()
    work = live_prices.plan(c, on)
    if not work.wants:
        return redirect("/investments/prices", live_prices.save(c, work, {}, []).summary())
    found, failed = await run_in_threadpool(live_prices.gather, work)
    return redirect("/investments/prices", live_prices.save(c, work, found, failed).summary())


@router.post("/prices/market/fill")
async def market_fill(request: Request):
    return _fill_from(container(request))


@router.post("/prices/market/update")
async def market_update(request: Request):
    return await _update(container(request), "/investments/prices")


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
        market.save(local_folder(c.data_dir) / pack_id)
        saved.append(pack_id)
        if pack_id not in followed:
            followed.append(pack_id)
    c.settings.set("market_packs", ",".join(followed) or "none")
    names = {r["id"]: r["name"] for r in pack_rows(c.data_dir, ())}
    done = f"Imported {', '.join(names.get(p, p) for p in saved)}." if saved else "Nothing was imported."
    if older:
        done += f" Kept your newer {', '.join(names.get(p, p) for p in older)}."
    return _fill_from(c, done)


@router.get("/prices/markets")
async def price_files(request: Request):
    """Settings › Price files: which exchanges' prices to download and keep."""
    c = container(request)
    return render(request, "investments/price_files.html",
                  rows=pack_rows(c.data_dir, chosen(c.settings.get("market_packs"))))


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
    picked = [p for p in form.getlist("pack") if p in known]
    dropped = [p for p in chosen(c.settings.get("market_packs")) if p not in picked]
    c.settings.set("market_packs", ",".join(picked) or "none")
    forget(c.data_dir, dropped)
    if form.get("update"):
        return await _update(c, "/investments/prices/markets")
    return redirect("/investments/prices/markets", "Saved. Download shared prices on Investment prices brings the markets you added.")


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
            values[asset_id] = to_decimal(str(raw), "value") / position.quantity
        count = c.assets.set_prices(day, values)
        for key, raw in form.items():
            if not key.startswith("rp_") or not str(raw).strip():
                continue
            asset_text, checkpoint = key[3:].split("_", 1)
            c.reevaluations.record_manual_price(int(asset_text), checkpoint,
                                                to_decimal(str(raw), "price"))
            count += 1
        c.reevaluations.process_due()
    except LightningError as exc:
        return redirect(f"/investments/prices?date={day}", exc.message)
    return redirect("/investments", f"Saved {count} price input{'s' if count != 1 else ''}; reevaluation catch-up completed." if count
                    else "No prices entered.")


@router.get("/reevaluations")
async def reevaluations_page(request: Request):
    c = container(request)
    return render(request, "investments/reevaluations.html", rows=c.reevaluations.history(),
                  pending=c.reevaluations.pending_prices())
