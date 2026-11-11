"""Activity's To review, one row per card (IV-3AY8; owner picks 2026-11-11). Each card's Primary is its kind's own verb:
a row nobody sorted *Looks right* (it files the row under the category it is usually given), a payment that looks monthly
*Track it*, deposit interest *Match to deposit*, a bank message *Looks right*; *Change* opens the thing itself and *Skip*
moves on. Two entries that look like one payment recorded twice *Delete the copy* (the preview-checked merge, undoable)
with Keep both beside it. The rest of the inbox's Activity items stay one card each with their own action."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from lightning.ui.row_sheet import category_for_party

SORT_DAYS = 90      # rows nobody sorted in the last three months; older ones stay on the register's To sort
SORT_CARDS = 40     # a queue a thumb can finish; the register holds the rest


@dataclass(frozen=True)
class ReviewCard:
    kind: str                      # sort | duplicate | recurring | interest | sms | other
    title: str
    detail: str = ""
    amount: Decimal | None = None
    day: str = ""
    verb: str = "Review"           # the Primary's words
    href: str = ""                 # the Primary opens this ...
    post: dict | None = None       # ... or posts this form: {action, fields}
    change: str = ""               # Change opens this
    change_label: str = "Change"
    second: dict | None = None     # a second answer beside Change: {label, action, fields}, posted
    review_id: str = ""            # an inbox item: Not now snoozes it
    popup: bool = False
    chips: tuple = field(default_factory=tuple)   # a sort card's other likely categories: ({id, label}, ...)


def _sort_cards(c, day: date) -> list[ReviewCard]:
    ids = c.reporting.unsorted_in_order(None, day - timedelta(days=SORT_DAYS), day)[:SORT_CARDS]  # not money
    if not ids:
        return []
    usual = c.transactions.usual_categories()
    pickable = {item.id for item in c.categories.pickable()}
    cards = []
    for txn_id in ids:
        txn = c.transactions.get(txn_id)
        party = c.counterparties.resolve(txn.counterparty) if txn.counterparty else None
        learned = category_for_party(party, usual, pickable)
        if learned is None and txn.counterparty:   # a payee never saved as a counterparty still has a usual category
            seen = (usual.get(txn.counterparty) or {}).get("category_id")
            learned = int(seen) if seen and int(seen) in pickable else None
        back = urlencode({"return_to": "/activity?tab=review"})
        amount = abs(c.transactions.summarize(txn).amount)
        title = txn.counterparty or txn.description or "A payment with no category"
        if learned:
            name = c.categories.get(learned).name
            cards.append(ReviewCard("sort", title, name, amount, txn.date, "Looks right",
                                    post={"action": f"/transactions/{txn_id}/category",
                                          "fields": {"category_id": learned, "return_to": "/activity?tab=review"}},
                                    change=f"/transactions/{txn_id}/sheet?change=1&{back}", popup=True))
        else:
            cards.append(ReviewCard("sort", title, "", amount, txn.date, "Choose a category",
                                    href=f"/transactions/{txn_id}/sheet?{back}", popup=True))
    return cards


DUPLICATE_DAYS = 90  # not money


def _duplicate_cards(c, day: date) -> list[ReviewCard]:
    from lightning.transactions.duplicates import possible_duplicates
    cards = []
    back = "/activity?tab=review"
    for keep_id, drop_id in possible_duplicates(c, day - timedelta(days=DUPLICATE_DAYS), day):  # not money
        keep, drop = c.transactions.get(keep_id), c.transactions.get(drop_id)
        fingerprint = c.transactions.merge_preview(keep_id, drop_id).fingerprint
        title = keep.counterparty or drop.counterparty or keep.description or "A payment"
        days = keep.date if keep.date == drop.date else f"{min(keep.date, drop.date)} · {max(keep.date, drop.date)}"
        cards.append(ReviewCard("duplicate", title, "Recorded twice? The copy goes; the first one stays, with both notes.",
                                abs(c.transactions.summarize(keep).amount), days, "Delete the copy",
                                post={"action": "/transactions/merge",
                                      "fields": {"keep_id": keep_id, "drop_id": drop_id, "fingerprint": fingerprint,
                                                 "return_to": back}},
                                change=f"/transactions/merge?keep={keep_id}&drop={drop_id}", change_label="Compare",
                                second={"label": "Keep both", "action": "/activity/keep-both",
                                        "fields": {"keep_id": keep_id, "drop_id": drop_id}}))
    return cards


def _recurring_cards(c, day: date) -> list[ReviewCard]:
    cards = []
    for s in c.planning.suggestions(day):
        query = urlencode({"kind": s.get("kind", "BILL"), "name": s["name"], "amount": s["amount"], "frequency": "MONTHLY",
                           "counterparty": s["name"], "account_id": s.get("account_id") or "",
                           "category_id": s.get("category_id") or "", "start_date": s.get("start_date", ""),
                           "match_tolerance_pct": s.get("match_tolerance_pct", "")})
        cards.append(ReviewCard("recurring", s["name"], "Looks monthly. Track it so the plan expects it.",
                                Decimal(str(s["amount"])), "", "Track it", href=f"/plan/items/new?{query}",
                                change="/plan/recurring", popup=True))
    return cards


def _inbox_card(item: dict) -> ReviewCard:
    href, label = item["href"], item["label"]
    if "interest" in label.lower() and href.startswith("/deposits/"):
        kind, verb = "interest", "Match to deposit"
    elif href.startswith("/sms"):
        kind, verb = "sms", "Looks right"
    else:
        kind, verb = "other", item.get("action") or "Review"
    return ReviewCard(kind, label, item.get("detail", ""), verb=verb, href=href, change=href,
                      review_id=item.get("review_id", ""), popup=bool(item.get("popup")))


def review_cards(c, day: date, inbox_items: list[dict]) -> list[ReviewCard]:
    """Rows to sort first (newest first), then possible duplicates, then payments that look monthly, then the inbox's
    other Activity items. The
    inbox's grouped "N payments have no category" item is left out: its rows are the sort cards."""
    rest = [i for i in inbox_items if not i["href"].startswith("/transactions?category_id=")]
    return [*_sort_cards(c, day), *_duplicate_cards(c, day), *_recurring_cards(c, day), *(_inbox_card(i) for i in rest)]
