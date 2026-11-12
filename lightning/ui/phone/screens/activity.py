"""Activity (IV-3AY8, guideline C11.4): "What moved, and what needs sorting?". All is the month's rows with one money
line; To review is one card at a time over the review inbox's sortable items, each with its one action and *Not now*.
Services calculate; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import month_of, parse_month
from lightning.transactions.domain import DocType
from lightning.workflows.review import ReviewInbox, group_of

TABS = ("all", "review")
ROWS = 120


@dataclass(frozen=True)
class ActivityScreen:
    tab: str
    month: str
    prev_month: str
    next_month: str            # "" for the current month
    rows: tuple                # register rows, newest first (All)
    money_in: Decimal
    money_out: Decimal
    review_total: int          # the To review count, on both tabs
    card: object | None        # the current ReviewCard (To review, 3AY8); None when the queue is clear
    index: int                 # 0-based position of the card
    more_rows: bool            # the month holds more rows than are drawn
    in_share: int = 0   # bar lengths (0-100) on one scale: the larger of In and Out is 100 (11D3)
    out_share: int = 0
    ledger_empty: bool = False   # IV-11A2: nothing was ever recorded: say so once, with Add and Import


def review_items(c, day: date) -> list[dict]:
    """The inbox's activity-group items, most urgent first: what sorting means on the phone."""
    return [i for i in ReviewInbox(c).items(day) if group_of(i) == "activity"]


def _shift(month: str, step: int) -> str:
    first, _ = parse_month(month)
    return month_of(first + timedelta(days=32) if step > 0 else first - timedelta(days=1))  # not money


def build(c, day: date, tab: str = "all", month: str = "", index: int = 0) -> ActivityScreen:
    tab = tab if tab in TABS else "all"
    this = month_of(day)
    try:
        start, end = parse_month(month or this)
    except Exception:
        start, end = parse_month(this)
    shown = month_of(start)
    items = review_items(c, day)
    from lightning.ui.phone.screens.review_cards import review_cards
    items = review_cards(c, day, items)   # one row per card, each with its kind's own verb (3AY8); one count on both tabs
    card = items[min(max(index, 0), len(items) - 1)] if items and tab == "review" else None  # not money
    rows: tuple = ()
    money_in = money_out = Decimal(0)
    more = False
    if tab == "all":
        page, total, _ = c.reporting.register_page(None, start, min(end, day), 1, ROWS)
        rows = tuple(r for r in page if r.type != DocType.VAL)
        more = total > ROWS
        flow = c.reporting.cash_flow(start, min(end, day))
        money_in, money_out = flow.inflows, flow.outflows
    top = max(money_in, money_out)
    in_share = int(round(money_in / top * 100)) if top > 0 else 0  # not money: the bar's width
    out_share = int(round(money_out / top * 100)) if top > 0 else 0  # not money: the bar's width
    return ActivityScreen(tab=tab, month=shown, prev_month=_shift(shown, -1),
                          next_month="" if shown >= this else _shift(shown, 1), rows=rows,
                          money_in=money_in, money_out=money_out, in_share=in_share, out_share=out_share, review_total=len(items), card=card,
                          index=items.index(card) if card else 0, more_rows=more,
                          ledger_empty=c.reporting.first_activity_date() is None)
