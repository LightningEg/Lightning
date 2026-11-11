"""The Spending page's period and totals, before any chart: which days it shows, what was spent in them and in the
period before. The PC page and the phone's Spending screen both start here (3AY11), so they answer for the same days
with the same figures and the phone layer never imports the PC routes."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from lightning.reporting.period_compare import total
from lightning.core.dates import month_of, today
from lightning.core.errors import LightningError
from lightning.reporting.spending import comparison_windows, partial_months

from .periods import Period, parse_period


def period_of(c, query):
    if str(query.get("period", "month")) == "custom" and (not query.get("date_from") or not query.get("date_to")):
        period = parse_period({"period": "month", "month": query.get("month", month_of(today()))}, today(), c.reporting.first_activity_date())
        return Period("custom", "Custom", period.start, period.end)
    return parse_period(query, today(), c.reporting.first_activity_date())


def facts(c, params) -> dict:
    """The Spending page's figures for the asked period. Every tab opens on the current month (owner, 2026-11-10,
    IV-12Y1): early in a month the lead compares the same days of earlier months instead of showing last month."""
    prior_from = prior_to = None
    try:
        selected = period_of(c, params)
        error = ""
    except LightningError as exc:
        fallback = period_of(c, {"period": "month", "month": month_of(today())})
        selected = Period("custom", "Custom", fallback.start, fallback.end) if params.get("period") == "custom" else fallback
        error = exc.message
    first, last = selected.start, selected.end
    flow = c.reporting.cash_flow(first, last)
    l1 = c.reporting.spending_by_category(first, last, depth=1)
    l2 = c.reporting.spending_by_category(first, last, depth=2)
    for group in l1 + l2:  # not money
        group.category_id = c.categories.get_by_code(group.code).id
    prior = None
    if selected.key != "all":
        if selected.key == "month":
            prior_to = first - timedelta(days=1)  # not money
            prior_from = prior_to.replace(day=1)
            prior_from, prior_to = comparison_windows(first, last, prior_from.strftime("%Y-%m"))[0]
        elif selected.key == "ytd":
            prior_from = date(first.year - 1, 1, 1)  # not money
            prior_to = date(first.year - 1, last.month, min(last.day, calendar.monthrange(first.year - 1, last.month)[1]))  # not money
        else:
            prior_to = first - timedelta(days=1)  # not money
            prior_from = prior_to - (last - first)  # not money
        prior = c.reporting.cash_flow(prior_from, prior_to)
    trend_first = first.replace(day=1)
    trend_count = (last.year - trend_first.year) * 12 + last.month - trend_first.month + 1  # not money
    trend_truncated = trend_count > 24
    if trend_count > 24:
        trend_first = last.replace(day=1)
        for _ in range(23):
            trend_first = (trend_first - timedelta(days=1)).replace(day=1)  # not money
    trend = c.reporting.monthly_flow_between(max(first, trend_first), last)
    category_filter = str(params.get("category_id", ""))
    category_code = ""
    category_name = ""
    selected_category = None
    if category_filter.isdigit():
        selected_category = c.categories.get(int(category_filter))
        category_code, category_name = selected_category.code, selected_category.name
        l2 = [x for x in l2 if x.code.startswith(category_code)]
        l1 = [x for x in l1 if category_code.startswith(x.code) or x.code.startswith(category_code)]
    if selected_category:
        depth = selected_category.depth
        def selected_spending(start, end):
            return total(group.value for group in c.reporting.spending_by_category(start, end, depth=depth)
                         if group.code == category_code)
        spending_total = selected_spending(first, last)
        prior_spending = selected_spending(prior_from, prior_to) if prior else None
        for item in trend:
            item["outflows"] = selected_spending(item["date_from"], item["date_to"])
    else:
        spending_total = flow.outflows
        prior_spending = prior.outflows if prior else None
    prior_label = (prior_from.strftime("%Y-%m") + (f" days {prior_from.day}–{prior_to.day}" if partial_months(first, last) else "") if selected.key == "month" else "the period before") if prior else ""  # not money
    return {"selected": selected, "error": error, "first": first, "last": last, "flow": flow, "l1": l1, "l2": l2, "prior": prior, "prior_from": prior_from, "prior_to": prior_to, "trend": trend, "trend_truncated": trend_truncated, "category_filter": category_filter, "category_code": category_code, "category_name": category_name, "spending_total": spending_total, "prior_spending": prior_spending, "prior_label": prior_label}
