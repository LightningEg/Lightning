"""Home's To do (IV-3AY6, guideline C04.4): the actions waiting on the person, one row each with one action, in the
order late or due-soon bill, payday, catch-up, to sort, weekly check, prices, then the rest. Bills come from the one
bill state (planning/bill_state.py); everything else from the review inbox, grouped as Needs you groups it."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.planning.bill_state import BillRow, BillState, CatchUp
from lightning.workflows.review import grouped

ORDER = ("bill", "payday", "catch_up", "sort", "weekly", "prices", "other")


@dataclass(frozen=True)
class TodoRow:
    kind: str                  # one of ORDER
    subject: str               # a bill's name, a group's label; the screen words the rest
    action: str                # the one action: Pay, Plan, Catch up, Sort, Review, Open
    href: str
    popup: bool = False
    amount: Decimal | None = None
    days: int | None = None    # bills: days until due (0 today); catch-up: days since the last entry
    late: int = 0              # bills: days late
    count: int = 1             # grouped items; catch-up: bills left stale
    since: str = ""            # catch-up: the last day anything was recorded


def todo_rows(c, day: date, bills: list[BillRow], inbox_items: list[dict], away: CatchUp,
              paid_today: bool = False) -> list[TodoRow]:
    """Every action waiting, most urgent first. The screen shows the first three and links to the rest.
    ``paid_today``: income arrived today or yesterday, the only time the payday row leads (C13)."""
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
        rows.append(TodoRow("payday", payday[0]["label"], "Plan", "/payday"))
    if away.away:
        rows.append(TodoRow("catch_up", "", "Catch up", "/sms", days=away.days_since_entry, count=away.stale_bills,
                            since=away.last_entry or ""))
    weekly = [i for i in others if i["href"] == "/review"]
    others = [i for i in others if i["href"] != "/review"]
    by_kind: dict[str, list[TodoRow]] = {"sort": [], "prices": [], "other": []}
    for g in grouped(others):
        kind = {"activity": "sort", "prices": "prices"}.get(g["key"], "other")
        by_kind[kind].append(TodoRow(kind, g["label"], "Sort" if kind == "sort" else "Review" if g["count"] == 1 else "Open",
                                     g["href"], popup=bool(g.get("popup")), count=g["count"]))
    rows += by_kind["sort"]
    if weekly:
        rows.append(TodoRow("weekly", weekly[0]["label"], "Review", "/review"))
    rows += by_kind["prices"] + by_kind["other"]
    return sorted(rows, key=lambda r: ORDER.index(r.kind))  # stable: bills keep their earliest-first order
