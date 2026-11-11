"""NF-7AQ3/5: Search answers a typed question ("food last month", "Carrefour 2026", "CIB last month", "#eid 2026")
with a figure, not a link.

The words are read by the period grammar (`core.periods`); what is left must name one category, account, payee or
tag (in that order; "#word" is always a tag) exactly or as the single clear match: an account's answer is its money
out, a tag's the money out of the transactions that carry it. The total comes from the reporting service (Spending's own figures), never
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
from lightning.transactions.tags import normalize as normal_tag

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
    found = None if subject.startswith("#") else (
        _category(c, subject, period) or _account(c, subject, period) or _payee(c, subject, period))
    found = found or _tag(c, subject, period)
    if not found:
        return None
    name, total, rows, count, link = found
    now, then = total(period), total(before)
    largest = sorted(rows, key=lambda row: abs(row.amount), reverse=True)[:ROWS]
    return {"name": name, "period": _period_label(period), "before_label": _period_label(before),
            "total": now, "before": then, "change": now - then, "count": count, "rows": largest,
            "href": "/transactions?" + urlencode(link | {"date_from": fmt_date(period.start),
                                                         "date_to": fmt_date(period.end)})}


def _between(period: Period) -> dict:
    return {"date_from": fmt_date(period.start), "date_to": fmt_date(period.end)}


def _category(c, subject: str, period: Period):
    categories = [(fold_search_text(cat.name), cat) for cat in c.categories.pickable()
                  if cat.code.startswith("EXP.") and subject in fold_search_text(cat.name)]
    category = _one(categories, subject)
    if not category:
        return None
    cat = category[1]
    ids = [cat.id] + [child.id for child in c.categories.descendants(cat.id)]

    def total(p: Period):
        spent = c.reporting.money_out_by_category(p.start, p.end)
        return sum((spent.get(i, ZERO) for i in ids), ZERO)

    rows, count = c.transactions.find(TxnFilter(category_ids=ids, limit=500, **_between(period)))
    return c.categories.display_name(cat.id), total, rows, count, {"category_id": cat.id}


def _account(c, subject: str, period: Period):
    """An account's money out: Spending's own lines paid from it (transfers between your accounts are not spent)."""
    accounts = [(fold_search_text(acc.name), acc) for acc in c.accounts.list(active_only=True)
                if subject in fold_search_text(acc.name)]
    account = _one(accounts, subject)
    if not account:
        return None
    acc = account[1]

    def total(p: Period):
        return dict(c.reporting.spending_by_account(p.start, p.end)).get(acc.id, ZERO)

    spent = {row["transaction_id"] for row in c.reporting.spending_lines(period.start, period.end)
             if row["account_id"] == acc.id}
    found, _ = c.transactions.find(TxnFilter(account_id=acc.id, limit=500, **_between(period)))
    rows = [row for row in found if row.id in spent and row.amount < 0]
    return acc.name, total, rows, len(rows), {"account_id": acc.id}


def _payee(c, subject: str, period: Period):
    payees = [(fold_search_text(who), who) for who, _ in c.reporting.spending_by_counterparty(period.start, period.end)
              if subject in fold_search_text(who)]
    payee = _one(payees, subject)
    if not payee:
        return None
    name = payee[1]

    def total(p: Period):
        return dict(c.reporting.spending_by_counterparty(p.start, p.end)).get(name, ZERO)

    found, _ = c.transactions.find(TxnFilter(search=name, limit=500, **_between(period)))
    rows = [row for row in found if fold_search_text(row.counterparty) == fold_search_text(name) and row.amount < 0]
    return name, total, rows, len(rows), {"q": name}


def _tag(c, subject: str, period: Period):
    """A tag's money out: Spending's own lines of the transactions whose notes carry it."""
    tag = normal_tag(subject)
    if not tag or tag not in dict(c.transactions.tags()):
        return None
    ids = c.transactions.tag_transaction_ids(tag)

    def total(p: Period):
        return sum((row["value"] for row in c.reporting.spending_lines(p.start, p.end)
                    if row["transaction_id"] in ids), ZERO)

    found, _ = c.transactions.find(TxnFilter(limit=500, **_between(period)))
    rows = [row for row in found if row.id in ids and row.amount < 0]
    return f"#{tag}", total, rows, len(rows), {"tag": tag}
