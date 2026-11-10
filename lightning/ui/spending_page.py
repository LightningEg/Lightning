"""The Spending page's period and totals, before any chart: which days it shows, what was spent in them and in the
period before. The PC page and the phone's Spending screen both start here (3AY11), so they answer for the same days
with the same figures and the phone layer never imports the PC routes."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from lightning.core.dates import month_of, today
from lightning.core.errors import LightningError
from lightning.core.money import ZERO
from lightning.reporting.spending import comparison_windows, partial_months

from .periods import Period, parse_period


def period_of(c, query):
    if str(query.get("period", "month")) == "custom" and (not query.get("date_from") or not query.get("date_to")):
        period = parse_period({"period": "month", "month": query.get("month", month_of(today()))}, today(), c.reporting.first_activity_date())
        return Period("custom", "Custom", period.start, period.end)
    return parse_period(query, today(), c.reporting.first_activity_date())


def facts(c, params, early_month: bool) -> dict:
    """``early_month``: early in a month with little to compare, lead with last month's whole picture and say in one
    line where this month stands (audit 12, SP1). The PC page asks for it; the phone's lead compares the same days
    instead, so it does not."""
    prior_from = prior_to = None
    try:
        selected = period_of(c, params)
        error = ""
    except LightningError as exc:
        fallback = period_of(c, {"period": "month", "month": month_of(today())})
        selected = Period("custom", "Custom", fallback.start, fallback.end) if params.get("period") == "custom" else fallback
        error = exc.message
    first, last = selected.start, selected.end
    # Early in a month (under 7 days, or under 3 categories with spending) the charts have nothing to compare, so the
    # page leads with last month's whole picture and says in one line where this month stands (audit 12, SP1).
    so_far = None
    plain = not any(key in params for key in ("period", "month", "date_from", "date_to", "category_id"))
    if plain and early_month and selected.key == "month" and not error and first <= today() <= last and last >= today():
        days = (today() - first).days + 1
        now_groups = [g for g in c.reporting.spending_by_category(first, last, depth=1) if g.value]
        categories = [g for g in c.reporting.spending_by_category(first, last, depth=2) if g.value]  # not the 3 groups
        if days < 7 or len(categories) < 3:
            before_last = first - timedelta(days=1)
            before_first = before_last.replace(day=1)
            if c.reporting.cash_flow(before_first, before_last).outflows > 0:
                so_far = {"month": month_of(first), "total": sum((g.value for g in now_groups), ZERO),
                          "categories": len(categories), "days": days}
                selected = Period("month", "Monthly", before_first, before_last)
                first, last = selected.start, selected.end
    flow = c.reporting.cash_flow(first, last)
    l1 = c.reporting.spending_by_category(first, last, depth=1)
    l2 = c.reporting.spending_by_category(first, last, depth=2)
    for group in l1 + l2:
        group.category_id = c.categories.get_by_code(group.code).id
    prior = None
    if selected.key != "all":
        if selected.key == "month":
            prior_to = first - timedelta(days=1)
            prior_from = prior_to.replace(day=1)
            prior_from, prior_to = comparison_windows(first, last, prior_from.strftime("%Y-%m"))[0]
        elif selected.key == "ytd":
            prior_from = date(first.year - 1, 1, 1)
            prior_to = date(first.year - 1, last.month, min(last.day, calendar.monthrange(first.year - 1, last.month)[1]))
        else:
            prior_to = first - timedelta(days=1)
            prior_from = prior_to - (last - first)
        prior = c.reporting.cash_flow(prior_from, prior_to)
    trend_first = first.replace(day=1)
    trend_count = (last.year - trend_first.year) * 12 + last.month - trend_first.month + 1
    trend_truncated = trend_count > 24
    if trend_count > 24:
        trend_first = last.replace(day=1)
        for _ in range(23):
            trend_first = (trend_first - timedelta(days=1)).replace(day=1)
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
            return sum((group.value for group in c.reporting.spending_by_category(start, end, depth=depth)
                        if group.code == category_code), ZERO)
        spending_total = selected_spending(first, last)
        prior_spending = selected_spending(prior_from, prior_to) if prior else None
        for item in trend:
            item["outflows"] = selected_spending(item["date_from"], item["date_to"])
    else:
        spending_total = flow.outflows
        prior_spending = prior.outflows if prior else None
    prior_label = (prior_from.strftime("%Y-%m") + (f" days {prior_from.day}–{prior_to.day}" if partial_months(first, last) else "") if selected.key == "month" else "the period before") if prior else ""
    return {"selected": selected, "error": error, "first": first, "last": last, "so_far": so_far, "flow": flow, "l1": l1, "l2": l2, "prior": prior, "prior_from": prior_from, "prior_to": prior_to, "trend": trend, "trend_truncated": trend_truncated, "category_filter": category_filter, "category_code": category_code, "category_name": category_name, "spending_total": spending_total, "prior_spending": prior_spending, "prior_label": prior_label}
