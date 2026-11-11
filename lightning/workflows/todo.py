"""Home's To do (IV-3AY6, IV-11E, guideline C04.4, C11.1): the actions waiting on the person, one row each with its
figure and one verb, in the order late or due-soon bill, payday, catch-up, to sort, weekly check, prices, then the
rest. Bills come from the one bill state (planning/bill_state.py); everything else from the review inbox, one row per
item, read from the item's glance."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.planning.bill_state import BillRow, BillState, CatchUp
from lightning.workflows.review import group_of

ORDER = ("bill", "payday", "catch_up", "sort", "weekly", "prices", "other")


@dataclass(frozen=True)
class TodoRow:
    """One row read at a glance (IV-11E, guideline C11.1): who or what, its figure, when or how many, one verb."""
    kind: str                  # one of ORDER
    subject: str               # a bill's or a thing's name; the screen words the rest
    action: str                # the one verb: Pay, Match, Top up, Make it a bill, Catch up, Sort, Plan...
    href: str
    popup: bool = False
    amount: Decimal | None = None
    days: int | None = None    # bills: days until due (0 today); catch-up: days since the last entry
    late: int = 0              # bills: days late
    count: int | None = 1      # catch-up: bills left stale; others: the {n} in ``when``
    since: str = ""            # catch-up: the last day anything was recorded; others: the {sa} in ``when``
    when: str = ""             # others: when or how many, a translatable phrase ("every month", "{n} to match")


def _row(kind: str, item: dict) -> TodoRow:
    """An inbox item as one To do row, from its glance (workflows.review.glance); an item without one keeps its label
    and its own action, and "Review" becomes "Open": every row says what happens."""
    g = item.get("glance")
    if g:
        return TodoRow(kind, g["name"], g["verb"], item["href"], popup=bool(item.get("popup")), amount=g.get("amount"),
                       count=g.get("n"), since=g.get("sa") or "", when=g.get("when") or "")
    action = item.get("action") or "Open"
    return TodoRow(kind, item["label"], "Open" if action == "Review" else action, item["href"],
                   popup=bool(item.get("popup")), count=None)


def todo_rows(c, day: date, bills: list[BillRow], inbox_items: list[dict], away: CatchUp,
              paid_today: bool = False) -> list[TodoRow]:
    """Every action waiting, most urgent first, one row per thing. The screen shows the first three and links to the
    rest. ``paid_today``: income arrived today or yesterday, the only time the payday row leads (C13)."""
    rows: list[TodoRow] = []
    for r in bills:
        if r.state in (BillState.LATE, BillState.DUE_SOON):
            p = r.payment
            rows.append(TodoRow("bill", p.item.name, "Pay",
                                f"/plan/items/{p.item.id}/pay?due={p.due_date}&back=%2F", popup=True,
                                amount=c.planning.amount_in_base(p, p.still_owed, day), days=r.days_until, late=r.late_days))
    others = [i for i in inbox_items if not i["label"].startswith(("Bill due:", "Loan payment due:"))]
    payday = [i for i in others if i["href"] == "/payday"]
    others = [i for i in others if i["href"] != "/payday"]
    if payday and paid_today:
        rows.append(_row("payday", payday[0]))
    if away.away:
        rows.append(TodoRow("catch_up", "", "Catch up", "/catch-up", days=away.days_since_entry, count=away.stale_bills,
                            since=away.last_entry or ""))
    for item in others:
        kind = "weekly" if item["href"] == "/review" else {"activity": "sort", "prices": "prices"}.get(group_of(item), "other")
        rows.append(_row(kind, item))
    return sorted(rows, key=lambda r: ORDER.index(r.kind))  # stable: bills earliest first, the rest in the inbox's order
