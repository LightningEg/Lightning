"""Chart data for pages: read figures from services, then shape them with lightning.ui.charts.

No financial calculation happens here: every value is a figure a service computed.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from lightning.core.dates import fmt_date, months_back, parse_date, parse_month
from lightning.core.money import ZERO, fmt

from lightning.planning.domain import PlanKind
from lightning.investments import journey
from lightning.reporting.spending import spending_profile

from . import charts


def spending_trend(c, end: date, category_code: str = "", count: int = 6) -> dict:
    """Money out per month, with the month's plan as a dashed line when one exists."""
    keys = months_back(end, count, c.reporting.first_activity_date())
    if not keys:
        return charts.trend([], [])
    if category_code:
        values = []
        depth = c.categories.get_by_code(category_code).depth
        for key in keys:
            first, last = parse_month(key)
            last = min(last, end)
            values.append(sum((g.value for g in c.reporting.spending_by_category(first, last, depth=depth)
                               if g.code == category_code), ZERO))
    else:
        rows = {r["month"]: r for r in c.reporting.monthly_flow_between(parse_month(keys[0])[0], end)}
        values = [rows.get(k, {}).get("outflows", ZERO) for k in keys]
    plan, over = None, None
    if not category_code:
        # Each month is over (or not) against its own plan; the dashed line is the latest month's.
        plans = [c.budgets.month_view(k).available if c.budgets.has_plan(k) else None for k in keys]
        over = [p is not None and v > p for p, v in zip(plans, values)]
        plan = plans[-1] or None
    return charts.trend(keys, [{"name": "Money out", "tone": "hold", "values": values, "area": True, "over": over}],
                        plan=plan)


def _leaf(name: str) -> str:
    return name.split(" › ")[-1]


def cash_flow_columns(c, first: date, last: date, cash_flow) -> dict:
    """Money in, less money out by top-level category (Personal, Work, ...), down to net flow."""
    groups = [g for g in c.reporting.spending_by_category(first, last, depth=1) if g.value]
    steps = [(_leaf(g.label), -g.value) for g in groups]
    rest = cash_flow.outflows - sum((g.value for g in groups), ZERO)
    if rest:  # anything the category tree does not carry, so the path still ends at net flow
        steps.append(("Other money out", -rest))
    return charts.column_waterfall(("Money in", cash_flow.inflows), steps, ("Net flow", cash_flow.net))


def money_out_groups(c, first: date, last: date) -> list[dict]:
    """Money out by top-level category, each linking to its transactions (the Cash flow list)."""
    rows = []
    for g in c.reporting.spending_by_category(first, last, depth=1):
        category = c.categories.get_by_code(g.code)
        query = urlencode({"category_id": category.id, "date_from": fmt_date(first), "date_to": fmt_date(last)})
        rows.append({"label": _leaf(g.label), "value": g.value, "href": f"/transactions?{query}"})
    return rows


def money_in_groups(c, first: date, last: date) -> list[dict]:
    """Money in by income category, largest first, each linking to its transactions."""
    rows = []
    for g in c.reporting.money_in_by_category(first, last):
        category = c.categories.get_by_code(g.code)
        query = urlencode({"category_id": category.id, "date_from": fmt_date(first), "date_to": fmt_date(last)})
        rows.append({"label": _leaf(g.label), "value": g.value, "href": f"/transactions?{query}"})
    return rows


def money_sankey(c, first: date, last: date, cash_flow, sources_shown: int = 3, targets_shown: int = 4,
                 money_added: Decimal = ZERO, xs: tuple[float, float, float] = (22.0, 49.0, 76.0)) -> dict:
    """Where money in went: income by category into money in, and money in out to spending
    categories and what you kept. When money out is larger, the gap comes from what you had.
    What you kept splits into the part you invested (blue) and the rest
    (feedback ticket 82); money added beyond what you kept came from earlier savings, so it is not shown."""
    incomes = money_in_groups(c, first, last)
    sources = [{**r, "tone": "in"} for r in incomes[:sources_shown]]
    rest_in = cash_flow.inflows - sum((r["value"] for r in sources), ZERO)
    if rest_in > 0:
        sources.append({"label": "Other income", "value": rest_in, "tone": "in"})
    if cash_flow.net < 0:
        sources.append({"label": "From what you had", "value": -cash_flow.net, "tone": "over"})
    spending, refunded = [], ZERO
    for g in c.reporting.spending_by_category(first, last, depth=2):
        if g.value < 0:
            refunded -= g.value  # a category whose refunds outweigh its spending: money that came back
            continue
        if g.value == 0:
            continue
        category = c.categories.get_by_code(g.code)
        query = urlencode({"category_id": category.id, "date_from": fmt_date(first), "date_to": fmt_date(last)})
        spending.append({"label": _leaf(g.label), "value": g.value, "tone": "spend", "href": f"/transactions?{query}"})
    if refunded > 0:
        # Money out already takes these refunds off; show them coming back in, so both sides of the
        # chart add up to the same total (audit 2026-10-05 #12).
        sources.append({"label": "Refunds", "value": refunded, "tone": "in"})
    targets = spending[:targets_shown]
    rest_out = cash_flow.outflows + refunded - sum((t["value"] for t in targets), ZERO)
    if rest_out > 0:
        targets.append({"label": "Other", "value": rest_out, "tone": "spend"})
    if cash_flow.net > 0:
        invested = min(max(money_added, ZERO), cash_flow.net)
        if invested > 0:
            targets.append({"label": "Invested", "value": invested, "tone": "hold"})
        if cash_flow.net - invested > 0:
            targets.append({"label": "Kept", "value": cash_flow.net - invested, "tone": "in"})
    return charts.sankey(sources, targets, "Money in", xs=xs)


def savings_rates(c, end: date, count: int = 6) -> list:
    """Savings rate for each recent month, the service's own figure (None for a month with no money in)."""
    return [c.reporting.cash_flow(parse_month(key)[0], day).savings_rate
            for key, day in month_ends(end, count, c.reporting.first_activity_date())]


def savings_rate_spark(c, end: date, count: int = 6) -> dict:
    """Savings rate for each recent month, as a sparkline."""
    return charts.sparkline(savings_rates(c, end, count))


def holdings_donut(position, include_cash: bool = False) -> dict:
    """What you hold by asset class, deposits included, in class colours (cash, deposits, gold, equity, other)."""
    slices = []
    if include_cash and position.cash_you_own:
        slices.append({"label": "Cash you own", "value": position.cash_you_own, "tone": "cash"})
    for cls in position.classes:
        slices.append({"label": cls.name, "value": cls.value, "tone": charts.class_tone(cls.code)})
    if include_cash and position.other_you_own > 0:
        slices.append({"label": "Other you own", "value": position.other_you_own, "tone": "other"})
    return charts.donut(slices)


def forecast_trend(forecast) -> dict:
    """The forecast's Ends with for each month."""
    labels = [m.month for m in forecast.months]
    values = [m.closing for m in forecast.months]
    return charts.trend(labels, [{"name": "Ends with", "tone": "hold", "values": values, "area": True}])


def month_ends(end: date, count: int, first_activity: str | None) -> list[tuple[str, date]]:
    """(yyyy-mm, month end) for up to ``count`` months ending with ``end`` (the last one is ``end``)."""
    out = []
    for key in months_back(end, count, first_activity):
        _, last = parse_month(key)
        out.append((key, min(last, end)))
    return out


def net_worth_trend(c, end: date, count: int = 12) -> dict:
    """Net worth at each month end (the same Position as the Overview's cards)."""
    ends = month_ends(end, count, c.reporting.first_activity_date())
    points = [(key, c.position.at(day)) for key, day in ends]
    owes = any(pos.what_you_owe for _, pos in points)
    # One line: the breakdown right under the chart carries What you own and What you owe.
    series = [{"name": "Net worth" if owes else "What you own", "tone": "hold", "area": True,
               "values": [pos.net_worth if owes else pos.what_you_own for _, pos in points]}]
    out = charts.trend([k for k, _ in points], series)
    # A month's rise can be an account added as already owned: say so, it is not a change (audit 2026-10-05).
    opened = c.reporting.opening_balances_by_month(ends[1][1].replace(day=1), end) if len(ends) > 1 else {}
    out["openings"] = [(key, opened[key]) for key, _ in ends[1:] if key in opened]
    return out


def free_cash_steps(position) -> dict | None:
    """Cash you own, less cash kept apart, reserves and bills due, down to free cash."""
    if position.free_cash is None:
        return None
    steps = [("Kept apart", -position.kept_apart)] if position.kept_apart else []
    return charts.waterfall(("Cash you own", position.cash_you_own),
                            steps + [("Reserves", -(position.reserves or ZERO)), ("Bills due", -position.bills_due)],
                            ("Free cash", position.free_cash))


def trend_spark(t: dict) -> dict:
    """The first series of a trend as a sparkline (a stat card's background line)."""
    series = t.get("series") or []
    return charts.sparkline(series[0]["values"] if series else [])


def usual_rows(rows: list[dict], limit: int = 10) -> list[dict]:
    """Categories against their usual month, each with a mini trend."""
    return [{**r, "label": r["label"].split(" › ")[-1], "group": r["label"].split(" › ")[0],
             "spark": charts.sparkline(r["history"])} for r in rows[:limit]]


def counterparty_bars(c, first: date, last: date, limit: int = 8) -> dict:
    """Who you paid most, each linking to their transactions."""
    rows = [{"label": name, "value": value,
             "href": "/transactions?" + urlencode({"q": name, "date_from": fmt_date(first), "date_to": fmt_date(last)})}
            for name, value in c.reporting.spending_by_counterparty(first, last)]
    return charts.bars(rows, limit)


def account_bars(c, first: date, last: date) -> dict:
    """Which accounts the spending was paid from."""
    names = {a.id: a.name for a in c.accounts.list()}
    rows = [{"label": names.get(account_id, "Account"), "value": value,
             "href": f"/accounts/{account_id}?" + urlencode({"month": fmt_date(last)[:7]}) if fmt_date(first)[:7] == fmt_date(last)[:7] else f"/accounts/{account_id}"}
            for account_id, value in c.reporting.spending_by_account(first, last)]
    return charts.bars(rows, 6)


def holding_journey(c, account_id: int, asset_id: int, end: date, months: int = 24) -> dict:
    """One holding's month-end history as charts; the figures come from `investments.journey`."""
    j = journey.holding_history(c.reporting, c.investments, account_id, asset_id, end, months)
    if not j["labels"]:
        return {"labels": [], "trades": []}
    labels, price, value, cost = j["labels"], j["price"], j["value"], j["cost"]
    currency = c.assets.get_asset(asset_id).currency
    foreign = currency != c.base_currency
    return {
        "currency": currency if foreign else None,
        "average_native": j["average_native"] if foreign else None,
        "labels": labels, "first": j["first"], "months_held": j["months_held"],
        "price": charts.trend(labels, [{"name": "Price", "tone": "hold", "values": price, "plan_applies": False}],
                              plan=j["average_native"] if foreign else j["average"]),
        "value_cost": charts.trend(labels, [{"name": "Value", "tone": "hold", "values": value, "area": True},
                                            {"name": "Cost", "tone": "other", "values": cost}]),
        "drawdown": charts.trend(labels, [{"name": "Below its high", "tone": "spend", "area": True,
                                           "values": j["drawdown"]}]),
        "returns": charts.diverging([{"label": k, "value": v} for k, v in j["returns"]]),
        "best": j["best"], "worst": j["worst"], "typical": j["typical"], "max_drawdown": j["max_drawdown"],
        "up": j["up"], "down": j["down"], "spark": charts.sparkline(value[-6:]), "trades": j["trades"],
    }


WEEK_STARTS_ON = 5  # Saturday (Python weekday), as calendars in Egypt run; Monday would be 0
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _ranked(values: list[Decimal]) -> list[Decimal]:
    """The sizes to rank against: every non-zero size, smallest first."""
    return sorted(abs(v) for v in values if v)


def _step(value: Decimal, ranked: list[Decimal]) -> int:
    """1–4 by rank among ``ranked``, in four equal groups; the largest is always 4 (darker is more)."""
    if not value or not ranked:
        return 0
    if len(ranked) == 1:
        return 4
    rank = bisect_right(ranked, abs(value)) - 1
    return min(4, 1 + rank * 4 // (len(ranked) - 1))


def day_calendars(c, first: date, last: date, code_filter: str = "", months: int = 12) -> dict:
    """Calendar heatmaps for the period, one small month per calendar month (the last ``months`` of a
    longer period): money out per day in rose steps, and net cash flow per day, green kept and rose
    short. Steps are by rank among the period's own days, so a rent day doesn't wash out the rest."""
    first_record = c.reporting.first_activity_date()
    first = max(first, parse_date(first_record)) if first_record else first  # nothing to show before it
    flows = c.reporting.flows_by_date(first, last, "day", code_filter)
    month_starts = []
    cursor = last.replace(day=1)
    while cursor >= first.replace(day=1) and len(month_starts) < months:
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()
    shown_from = max(first, month_starts[0]) if month_starts else first
    spend = {k: v["spending"] for k, v in flows.items() if k >= fmt_date(shown_from)}
    net = {k: v["net"] for k, v in flows.items() if k >= fmt_date(shown_from)}
    spend_rank, net_rank = _ranked(list(spend.values())), _ranked(list(net.values()))
    order = [(WEEK_STARTS_ON + i) % 7 for i in range(7)]

    def grid(start: date) -> list[list[dict | None]]:
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        weeks, week = [], [None] * order.index(start.weekday())
        day = start
        while day <= end:
            key = fmt_date(day)
            inside = first <= day <= last
            s, n = spend.get(key, ZERO), net.get(key, ZERO)
            week.append({"day": day.day, "date": key, "inside": inside, "spend": s, "net": n,
                         "spend_step": _step(s, spend_rank) if s > 0 else 0,
                         "net_step": _step(n, net_rank), "net_tone": "in" if n > 0 else "out" if n < 0 else "zero"})
            if len(week) == 7:
                weeks.append(week); week = []
            day += timedelta(days=1)
        if week:
            weeks.append(week + [None] * (7 - len(week)))
        return weeks

    cal = [{"key": m.strftime("%Y-%m"), "name": f"{MONTH_NAMES[m.month - 1]} {m.year}", "weeks": grid(m)}
           for m in month_starts]
    spend_days = [(k, v) for k, v in spend.items() if v > 0]
    busiest = max(spend_days, key=lambda kv: kv[1]) if spend_days else None
    days_in = (last - shown_from).days + 1
    monthly_flows = c.reporting.flows_by_date(first, last, "month", code_filter)
    monthly = [{"key": key, "spend": values["outflows"], "net": values["net"]}
               for key, values in sorted(monthly_flows.items())]
    return {"months": cal, "weekdays": [WEEKDAYS[i] for i in order], "single": len(cal) == 1,
            "long_period": days_in > 92, "monthly": monthly,
            "busiest": busiest, "spend_days": len(spend_days), "days": days_in,
            "quiet_days": days_in - len(spend_days),
            "kept_days": sum(1 for v in net.values() if v > 0), "short_days": sum(1 for v in net.values() if v < 0),
            "cut_note": len(month_starts) == months and first.replace(day=1) < month_starts[0]}


def month_calendar(c, last: date, years: int = 5) -> dict:
    """Calendar heatmap by month for the Overview: one row per year (the last ``years``), twelve
    months across; money out in rose steps and net cash flow in green and rose, four steps over all the
    months shown, by rank. A fixed horizon: every month since the first record, up to the month of ``last``."""
    first_record = c.reporting.first_activity_date()
    if not first_record:
        return {"years": []}
    start = max(parse_date(first_record).replace(day=1), date(last.year - years + 1, 1, 1))
    flows = c.reporting.flows_by_date(start, last, "month")
    spend_rank = _ranked([v["outflows"] for v in flows.values() if v["outflows"] > 0])
    net_rank = _ranked([v["net"] for v in flows.values()])
    rows = []
    for year in range(start.year, last.year + 1):
        cells = []
        for m in range(1, 13):
            key = f"{year}-{m:02d}"
            known = start.strftime("%Y-%m") <= key <= last.strftime("%Y-%m")
            f = flows.get(key, {"outflows": ZERO, "net": ZERO, "inflows": ZERO})
            cells.append({"key": key, "month": MONTH_NAMES[m - 1], "known": known, "spend": f["outflows"],
                          "net": f["net"], "inflows": f["inflows"],
                          "spend_step": _step(f["outflows"], spend_rank) if known and f["outflows"] > 0 else 0,
                          "net_step": _step(f["net"], net_rank) if known else 0,
                          "net_tone": "in" if f["net"] > 0 else "out" if f["net"] < 0 else "zero"})
        rows.append({"year": year, "cells": cells})
    known = [cell for r in rows for cell in r["cells"] if cell["known"]]
    best = max(known, key=lambda x: x["net"]) if known else None
    biggest = max(known, key=lambda x: x["spend"]) if known else None
    return {"years": rows, "months": MONTH_NAMES, "best": best, "biggest": biggest,
            "kept": sum(1 for x in known if x["net"] > 0), "short": sum(1 for x in known if x["net"] < 0),
            "count": len(known), "from": start.strftime("%Y-%m")}


def _range_marks(low, high, median, now) -> dict | None:
    """Positions on a usual-range bar that is the same size on every row: the pill runs from the
    lowest month (8%) to the highest (92%); the middle month and now sit where they fall, and a month
    outside the range sits in the margin at that end."""
    if low is None:
        return None
    span = high - low

    def at(v):
        if not span:
            return 50.0
        return float(max(Decimal(2), min(Decimal(98), 8 + (v - low) / span * 84)))
    return {"low": 8.0 if span else 50.0, "high": 92.0 if span else 50.0, "median": at(median), "now": at(now)}


def expense_analysis(c, first: date, last: date, code_filter: str = "", history: int = 12,
                     floor_share: Decimal = Decimal(1), top: int = 4) -> dict:
    """Expense analysis in five questions, big items only: the figures come from
    `reporting.spending.spending_profile`; this only shapes them into charts."""
    profile = spending_profile(c.reporting, first, last, code_filter, history, floor_share, top)
    rows, keys, months_in = profile["rows"], profile["history_keys"], profile["months_in"]
    for r in rows:
        r["range"] = _range_marks(r["low"], r["high"], r["median"], r["per_month"])
        r["href"] = (f"/transactions?date_from={fmt_date(first)}&date_to={fmt_date(last)}" if r.get("others") else
                     f"/transactions?category_id={c.categories.get_by_code(r['code']).id}"
                     f"&date_from={fmt_date(first)}&date_to={fmt_date(last)}")
    tiles = charts.treemap([{"label": r["name"], "value": r["value"], "share": r["share"], "href": r["href"],
                             "small": r.get("others", False)} for r in rows])
    # Clustered columns: usual month (neutral) beside now (its meaning colour), one scale, from zero.
    col_max = max([r["per_month"] for r in rows] + [r["usual"] or ZERO for r in rows] + [ZERO]) or Decimal(1)
    clusters = [{"name": r["name"], "now": r["per_month"], "usual": r["usual"],
                 "over": r["over_usual"] and not profile["partial"], "change": r["change_vs_usual"],
                 "now_h": float(r["per_month"] / col_max * 100), "usual_h": float((r["usual"] or ZERO) / col_max * 100)}
                for r in rows[:5]]
    # Small multiples: the same twelve months plus now, one scale for every panel.
    panels = rows[:4]
    lines = charts.shared_lines([r["past"] + [r["per_month"]] for r in panels])
    multiples = [{"name": r["name"], "now": r["per_month"], "line": line, "points": len(r["past"]) + 1}
                 for r, line in zip(panels, lines)]
    # Heatmap: category by month, each cell against that row's own average (four rose steps). The
    # history months, then every month of the period itself (a period of three months shows three).
    period_keys = profile["period_keys"]
    past_cols = keys[-max(1, 12 - len(period_keys)):] if keys else []
    heat_keys = past_cols + period_keys
    now_from = len(past_cols)
    heat = []
    for r in rows:
        values = (r["past"][-len(past_cols):] if past_cols else []) + r["period_values"]
        known = [v for v in values if v > 0]
        avg = sum(known, ZERO) / len(known) if known else ZERO
        cells = []
        for v in values:
            ratio = v / avg if avg else ZERO
            step = 0 if v <= 0 else 1 if ratio < Decimal("0.75") else 2 if ratio < Decimal("1.1") else 3 if ratio < Decimal("1.5") else 4
            cells.append({"value": v, "step": step})
        heat.append({"name": r["name"], "cells": cells})
    # Net cash flow by month, the same months: money in, money out and what was left.
    flow_rows = {"Money in": [], "Money out": [], "Net flow": []}
    for k in heat_keys:
        start, end = parse_month(k)
        start, end = (max(start, first), min(end, last)) if k in period_keys else (start, end)
        f = c.reporting.cash_flow(start, end)
        flow_rows["Money in"].append(f.inflows); flow_rows["Money out"].append(f.outflows); flow_rows["Net flow"].append(f.net)

    def steps(values, tone):
        known = [v for v in values if v > 0]
        avg = sum(known, ZERO) / len(known) if known else ZERO
        out = []
        for v in values:
            ratio = v / avg if avg else ZERO
            step = 0 if v <= 0 else 1 if ratio < Decimal("0.75") else 2 if ratio < Decimal("1.1") else 3 if ratio < Decimal("1.5") else 4
            out.append({"value": v, "step": step, "tone": tone})
        return out

    top_net = max((abs(v) for v in flow_rows["Net flow"]), default=ZERO) or Decimal(1)
    net_cells = [{"value": v, "tone": "in" if v > 0 else "out" if v < 0 else "zero",
                  "step": 0 if not v else min(4, 1 + int(abs(v) / top_net * 4 - Decimal("0.0001")))} for v in flow_rows["Net flow"]]
    flow_heat = [{"name": "Money in", "cells": steps(flow_rows["Money in"], "in")},
                 {"name": "Money out", "cells": steps(flow_rows["Money out"], "out")},
                 {"name": "Net flow", "cells": net_cells, "net": True}]
    return {"rows": rows, "refunds": profile["refunds"], "total": profile["total"], "small": profile["small"], "months_in": months_in,
            "tiles": tiles, "clusters": clusters, "multiples": multiples, "heat": heat, "heat_keys": heat_keys,
            "heat_now": now_from, "flow_heat": flow_heat, "history_months": len(keys),
            "usual_total": profile["usual_total"], "usual_out": profile["usual_out"], "per_month": profile["per_month"],
            "has_history": len(keys) >= 1, "has_range": len(keys) >= 3, "partial": profile["partial"]}


def cash_plan(c, forecast, day: date) -> dict:
    """Cash planning in four questions: the gist (stat cards), how safe to spend is worked out, where
    cash is heading (actual month ends, then the forecast) and what is promised."""
    f = forecast
    parts = dict(f.safe_to_spend_parts)
    steps = [(name, value) for name, value in f.safe_to_spend_parts[1:]]
    build = charts.waterfall((f.safe_to_spend_parts[0][0], f.free_cash), steps, ("Safe to spend", f.safe_to_spend))
    # Next 30 days on one date axis from today: money in above the line, bills below.
    end = day + timedelta(days=30)
    upcoming = [p for p in c.planning.all_payments(end, day) if p.status.value in ("DUE", "UPCOMING")]
    # One row of labels on each side (feedback ticket 94: three stacked rows were hard to read). A payment that
    # would touch the previous label on its side joins it: "Landlord +2" with their total, so payments already
    # due pile into one mark at Today. Each label is 92px; 22% of the axis is about 115px at 1,366px.
    marks, last = [], {True: None, False: None}
    for p in sorted(upcoming, key=lambda p: (p.due_date, -p.amount)):
        offset = max(0, (parse_date(p.due_date) - day).days)
        x = 3 + 94 * min(offset, 30) / 30
        late = p.status.value == "DUE"
        mark = last[p.item.is_income]
        if mark is not None and x - mark["x"] < 22:
            mark["count"] += 1
            mark["amount"] += p.amount
            mark["late"] = mark["late"] or late
            mark["title"] += f"\n{p.item.name} · {p.due_date} · {fmt(p.amount, 0)}"
            continue
        mark = {"name": p.item.name, "amount": p.amount, "income": p.item.is_income, "due": p.due_date,
                "x": x, "row": 0, "late": late, "count": 1, "title": f"{p.item.name} · {p.due_date} · {fmt(p.amount, 0)}"}
        last[p.item.is_income] = mark
        marks.append(mark)
    before_income = f.payments_before_income   # the same payments Safe to spend takes off
    # Where cash is heading: free cash at the last five month ends, then the forecast's month ends.
    past_keys = months_back(day.replace(day=1) - timedelta(days=1), 5, c.reporting.first_activity_date())
    past = []
    for key in past_keys:
        pos = c.position.at(parse_month(key)[1])
        past.append(pos.free_cash)
    future_keys = [m.month for m in f.months]
    labels = past_keys + future_keys
    actual = past + [None] * len(future_keys)
    ahead = ([None] * (len(past_keys) - 1) + [past[-1]] if past_keys else []) + [m.closing for m in f.months]
    over = [False] * len(past_keys) + [m.closing < 0 for m in f.months]
    series = []
    if past_keys:
        series.append({"name": "Free cash", "tone": "hold", "values": actual, "area": True})
    series.append({"name": "Forecast", "tone": "hold", "values": ahead, "dashed": True, "over": over})
    heading = charts.trend(labels, series)
    # In and out for each month ahead: money in up, what goes out down, one scale.
    # This month is only what is left of it: what already came in is in Free cash, not here.
    rows = [{"month": m.month, "rest": m.month == day.strftime("%Y-%m"), "income": m.income, "deposit_cash": m.deposit_cash, "circle_in": m.circle_in, "circle_out": m.circle_out, "in": m.money_in,
             "commitments": m.commitments, "budget_spending": m.budget_spending, "goal_saving": m.goal_saving,
             "emergency_saving": m.emergency_saving, "target_saving": m.target_saving,
             "out": m.money_out, "net": m.net, "estimated": m.income_estimated}
            for m in f.months]
    top = max([r["in"] for r in rows] + [r["out"] for r in rows] + [ZERO]) or Decimal(1)
    for r in rows:
        r["in_h"], r["out_h"] = float(r["in"] / top * 100), float(r["out"] / top * 100)
    # What is promised: each loan's money still to pay, largest first, four then Other.
    loans = []
    for item in c.planning.items((PlanKind.LOAN,)):
        progress = c.planning.loan_progress(item, day)
        if progress["still_to_pay"] > 0:
            loans.append({"label": item.name, "value": c.planning.amount_in_base(item, progress["still_to_pay"], day),
                          "note": f"ends {progress['last_date']}" if progress["last_date"] else ""})
    loans.sort(key=lambda r: -r["value"])
    if len(loans) > 4:
        rest = loans[4:]
        loans = loans[:4] + [{"label": "Other", "value": sum((r["value"] for r in rest), ZERO), "note": f"{len(rest)} loans"}]
    return {"build": build, "marks": marks, "upcoming": upcoming, "before_income": before_income,
            "before_total": f.payments_before_income_total, "heading": heading, "flows": rows,
            "loan_bars": charts.bars(loans, 6), "loan_rows": loans, "forecast_spark": charts.sparkline([m.closing for m in f.months]),
            "parts": parts, "past_free": [(key, value) for key, value in zip(past_keys, past)]}


PAIR_XS = (24.0, 45.0, 64.0)  # two Sankeys side by side: target names get a third of each (style.css .is-pair)


def cash_flow_charts(c, first: date, last: date, month_period: bool, today_: date) -> dict:
    """Spending's Cash flow section (moved from the Overview, owner 2026-10-21): where the period's money in went,
    beside the last six months' when the period is a month (ticket 78), and net cash flow by month (tickets 79, 86)."""
    from lightning.investments.report import investment_period
    flow = c.reporting.cash_flow(first, last)
    added = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(first), fmt_date(last))["net_money"]
    six, six_from = None, None
    if month_period:
        keys = months_back(last, 6, c.reporting.first_activity_date())
        if len(keys) > 1:
            six_from = parse_month(keys[0])[0]
            six_added = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(six_from), fmt_date(last))["net_money"]
            six = money_sankey(c, six_from, last, c.reporting.cash_flow(six_from, last), money_added=six_added, xs=PAIR_XS)
    return {"money_sankey": money_sankey(c, first, last, flow, money_added=added, xs=PAIR_XS if six else (22.0, 49.0, 76.0)),
            "money_sankey_six": six, "six_from": six_from.strftime("%Y-%m") if six_from else "",
            "month_calendar": month_calendar(c, today_)}
