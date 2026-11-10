"""The phone's Search (templates/phone/search.html, guideline C03.2): money first, then names, then pages; live as you
type, so the page asks for the results alone as the words change (3AN6). Same matcher as the PC (3AY11)."""
from __future__ import annotations

from urllib.parse import urlencode

from lightning.core.money import ascii_digits
from lightning.ui.search_index import matches
from lightning.ui.web import privacy_on

PAYMENTS_SHOWN = 8  # the phone's Search lists this many payments, newest first, then "See all"


def phone_results(c, query: str, privacy: bool = False) -> dict:
    """What the phone's Search shows (3AN6, guideline C03.2): money first. Payments that match the words or the amount,
    newest first with their rows as the Transactions list draws them; then the names behind them (counterparties,
    categories, accounts, tags, holdings); then pages and actions under their own heading. The matching is `matches`
    and the transactions' own search; nothing here changes anything."""
    query = " ".join(str(query or "").split())
    found = matches(c, query, privacy=privacy, per_group=5)
    pages = [row for row in found if row["kind"] in ("Page", "Action")]
    money = [row for row in found if row["kind"] in ("Person", "Counterparty", "Category", "Account", "Reserve", "Tag", "Investment")]
    payments, total = [], 0
    if query:
        ordered = c.reporting.newest_first(c.transactions.search_ids(ascii_digits(query)))
        rows = c.reporting.rows_for_transactions(ordered[:PAYMENTS_SHOWN])
        payments, total = [row for row in rows if row.type != "VAL"], len(ordered)
    return {"query": query, "payments": payments, "payments_total": total, "money": money, "pages": pages,
            "see_all": "/transactions?" + urlencode({"q": query})}


def present(request, c, context: dict) -> dict:
    found = phone_results(c, context["query"], privacy=privacy_on(request))
    return {**found, "__template__": "search_results.html"} if request.query_params.get("fragment") else found
