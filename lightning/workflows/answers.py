"""NF-7AQ3: Search answers a typed question ("food last month", "Carrefour 2026") with a figure, not a link.

The words are read by the period grammar (`core.periods`); what is left must name one category or one payee
exactly or as the single clear match. The total comes from the reporting service (Spending's own figures), never
from the rows shown; the rows are only the largest few, and "Open in Transactions" carries the same filter.
Anything else returns None, and the search page shows today's results.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from lightning.core.dates import fmt_date
from lightning.core.matching import fold_search_text
from lightning.core.money import ZERO
from lightning.core.periods import Period, month, read_period
from lightning.transactions.domain import TxnFilter

ROWS = 5


def _period_label(period: Period) -> str:
    return period.start.strftime("%B %Y") if period.kind == "month" else str(period.start.year)


def _one(found: list, subject: str):
    """The match when there is exactly one, or one whose name is the subject itself."""
    exact = [item for item in found if item[0] == subject]
    return exact[0] if len(exact) == 1 else found[0] if len(found) == 1 else None


def answer(c, text: str, today: date) -> dict | None:
    subject, period = read_period(text, today)
    if len(subject) < 3:
        return None
    period = period or month(today.year, today.month)
    before = period.before()
    categories = [(fold_search_text(cat.name), cat) for cat in c.categories.pickable()
                  if cat.code.startswith("EXP.") and subject in fold_search_text(cat.name)]
    category = _one(categories, subject)
    if category:
        cat = category[1]
        ids = [cat.id] + [child.id for child in c.categories.descendants(cat.id)]

        def total(p: Period):
            spent = c.reporting.money_out_by_category(p.start, p.end)
            return sum((spent.get(i, ZERO) for i in ids), ZERO)

        rows, count = c.transactions.find(TxnFilter(category_ids=ids, date_from=fmt_date(period.start),
                                                    date_to=fmt_date(period.end), limit=500))
        link = {"category_id": cat.id}
        name = c.categories.display_name(cat.id)
    else:
        payees = {}
        for who, spent in c.reporting.spending_by_counterparty(period.start, period.end):
            if subject in fold_search_text(who):
                payees[who] = spent
        payee = _one([(fold_search_text(who), who) for who in payees], subject)
        if not payee:
            return None
        name = payee[1]

        def total(p: Period):
            return dict(c.reporting.spending_by_counterparty(p.start, p.end)).get(name, ZERO)

        found, _ = c.transactions.find(TxnFilter(search=name, date_from=fmt_date(period.start),
                                                 date_to=fmt_date(period.end), limit=500))
        rows = [row for row in found if fold_search_text(row.counterparty) == fold_search_text(name)
                and row.amount < 0]
        count = len(rows)
        link = {"q": name}
    now, then = total(period), total(before)
    largest = sorted(rows, key=lambda row: abs(row.amount), reverse=True)[:ROWS]
    return {"name": name, "period": _period_label(period), "before_label": _period_label(before),
            "total": now, "before": then, "change": now - then, "count": count, "rows": largest,
            "href": "/transactions?" + urlencode(link | {"date_from": fmt_date(period.start),
                                                         "date_to": fmt_date(period.end)})}
