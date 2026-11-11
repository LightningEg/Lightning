"""Spending on the phone (3AN12): the lead (spent against the same days usually), the four biggest categories then
Other, then one row "More analysis" whose sheet loads the rest when it opens. The days and totals come from
``lightning.ui.spending_page``, the same start the PC page has."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from lightning.core.dates import fmt_date, month_of, today
from lightning.core.money import ZERO, fmt
from lightning.reporting.spending import partial_months
from lightning.ui import spending_page, visuals


def _compare(label: str, now: Decimal, then: Decimal | None, first, last) -> dict:
    """One comparison row: the difference and its share, rose when spending rose, green when it fell; a part-month
    reads flat (same days, so far)."""
    if then is None:
        return {"label": label, "text": "nothing to compare yet", "tone": "flat"}
    diff = now - then
    pct = f" · {abs(diff) / then * 100:.0f}%" if then else ""
    return {"label": label, "text": f"{'+' if diff > 0 else '−' if diff < 0 else ''}{fmt(abs(diff), 0)}{pct}",
            "tone": "flat" if partial_months(first, last) else ("up" if diff > 0 else "down" if diff < 0 else "flat")}


PHONE_CATEGORIES = 4  # four biggest, then Other (guideline A16)


def build(request, c) -> dict:
    """Spending on the phone (3AN12): the lead (spent against the same days usually), the four biggest categories then
    Other as rows, then one row "More analysis" whose sheet loads the heat map, the money-flow diagrams, the small
    multiples and the month grid when it opens. A month with nothing spent yet offers last month (3AN9)."""
    f = spending_page.facts(c, request.query_params)
    selected, first, last, total, prior_total = f["selected"], f["first"], f["last"], f["spending_total"], f["prior_spending"]
    prior_label, category_filter, category_code = f["prior_label"], f["category_filter"], f["category_code"]
    analysis = visuals.expense_analysis(c, first, last, category_code)
    months, usual = analysis["months_in"], analysis.get("usual_out")
    partial = partial_months(first, last)
    compare = [_compare("Against the same days in earlier months" if partial else
                        f"Against your usual {'month' if months == 1 else 'months'}",
                        total, usual * months if usual is not None else None, first, last),
               _compare(f"Against {prior_label}" if prior_label else "Against the period before", total, prior_total,
                        first, last)]
    query = (f"category_id={category_filter}&" if category_filter else "") + f"date_from={fmt_date(first)}&date_to={fmt_date(last)}"
    named = [r for r in analysis["rows"] if not r.get("others")]
    rest = named[PHONE_CATEGORIES:] + [r for r in analysis["rows"] if r.get("others")]
    other = ({"name": "Other", "value": sum((r["value"] for r in rest), ZERO), "share": sum((r["share"] for r in rest), ZERO),
              "href": f"/transactions?{query}"} if rest else None)
    earlier = None
    if total == 0 and selected.key == "month" and not category_filter:
        start = (first - timedelta(days=1)).replace(day=1)
        spent = c.reporting.cash_flow(start, first - timedelta(days=1)).outflows
        if spent > 0:
            earlier = {"month": month_of(start), "value": spent,
                       "href": f"/birdview/expenses?period=month&month={month_of(start)}"}
    return dict(period=selected.key, month=last.strftime("%Y-%m"),
                  this_month=month_of(today()), date_from=fmt_date(first), date_to=fmt_date(last),
                  custom_from=request.query_params.get("date_from", ""), custom_to=request.query_params.get("date_to", ""),
                  category_filter=category_filter, category_name=f["category_name"], error=f["error"], base=c.reporting.base_currency,
                  total=total, partial=bool(partial), compare=compare, rows=named[:PHONE_CATEGORIES], other=other, earlier=earlier,
                  more_query=urlencode(request.query_params), lead_href=f"/transactions?{query}")


def more(request, c) -> dict:
    """The "More analysis" sheet: what the first page leaves out, drawn when the sheet opens (3AN12)."""
    selected = spending_page.period_of(c, request.query_params)
    first, last = selected.start, selected.end
    category_filter = str(request.query_params.get("category_id", ""))
    category_code = c.categories.get(int(category_filter)).code if category_filter.isdigit() else ""
    analysis = visuals.expense_analysis(c, first, last, category_code)
    largest = c.reporting.largest_payments(first, last, 3)
    for row in largest:
        row["category"] = c.categories.get(row["category_id"]).name if row["category_id"] else ""
    payments = [r["value"] for r in c.reporting.largest_payments(first, last, 10 ** 6)] if not category_code else []
    flows = visuals.cash_flow_charts(c, first, last, selected.key == "month", today()) if not category_filter else {}
    return dict(**flows, analysis=analysis, largest=largest,
                  average=(sum(payments, ZERO) / len(payments)) if payments else None, payment_count=len(payments),
                  calendar=visuals.day_calendars(c, first, last, category_code), date_from=fmt_date(first),
                  date_to=fmt_date(last), base=c.reporting.base_currency, category_filter=category_filter)
