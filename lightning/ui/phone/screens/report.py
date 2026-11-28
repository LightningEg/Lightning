"""The period report on the phone (IV-3AY11 prerequisite): "How did a period go?". Home is always today, so the
Overview's month, year and all-time reading lives here, behind Money: the change in net worth, money in, out and
kept, the savings rate, and what investing did. Services calculate; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import fmt_date, month_of
from lightning.core.errors import LightningError
from lightning.investments.report import investment_period
from lightning.planning.position import net_worth_bridge
from lightning.ui.periods import parse_period

KEYS = ("month", "last", "ytd", "all", "custom")


@dataclass(frozen=True)
class ReportScreen:
    key: str
    label: str                       # "2026-10", "Year to date", "All time"
    start: str
    end: str
    change: Decimal | None           # change in net worth (owner, 2026-11-28); None when a valuation is missing
    change_reason: str
    money_in: Decimal
    money_out: Decimal
    net: Decimal
    savings_rate: Decimal | None
    investing_result: Decimal | None  # the period's gain or loss on holdings; None when a price is missing
    keys: tuple[tuple[str, str], ...]
    since: str = ""                  # NF-7BF: the day before the period, what "richer" is measured against
    bridge: dict | None = None       # why net worth changed (planning.position.net_worth_bridge), as on the PC Overview
    gold_change: Decimal | None = None   # the change in net worth in grams of 21K gold; None when a gold price is missing


def _period(c, day: date, key: str, date_from: str = "", date_to: str = ""):
    first = c.reporting.first_activity_date()
    if key == "custom":   # 3AY10: the report takes your own dates, as the older Overview's Custom did
        return parse_period({"period": "custom", "date_from": date_from, "date_to": date_to}, day, first)
    if key == "last":
        before = date(day.year - 1, 12, 1) if day.month == 1 else date(day.year, day.month - 1, 1)  # not money
        return parse_period({"period": "month", "month": month_of(before)}, day, first)
    return parse_period({"period": key if key in ("ytd", "all") else "month"}, day, first)


def build(c, day: date, key: str = "month", date_from: str = "", date_to: str = "") -> ReportScreen:
    key = key if key in KEYS else "month"
    try:
        period = _period(c, day, key, date_from, date_to)
    except LightningError:
        key = "month"
        period = _period(c, day, key)
    start, end = period.start, period.end
    flow = c.reporting.cash_flow(start, end)
    # Owner, 2026-11-28 (r40 decision 1A): the Report leads with Change in net worth, as the PC Overview does, so the
    # lead, the verdict and Why it changed are one figure.
    change, reason = c.position.change_in_net_worth(start, end, since_first_record=key == "all")
    investing = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(start), fmt_date(end))
    label = (month_of(start) if key in ("month", "last") else
             f"{fmt_date(start)} – {fmt_date(end)}" if key == "custom" else period.label)
    # NF-7BF: did the period leave you richer, why, and in gold: the PC Overview's net worth bridge (OV-3) and its gold
    # side, both worked out in planning/position.py.
    before = start - timedelta(days=1)  # not money: the day before the period
    bridge = net_worth_bridge(change, flow.net, investing)
    gold = (c.position.change_in_gold(start, end, c.zakat.gold_price_24k(fmt_date(before)), c.zakat.gold_price_24k(fmt_date(end)))
            if bridge else None)
    return ReportScreen(key=key, label=label, start=fmt_date(start), end=fmt_date(end), change=change,
                        change_reason=reason, money_in=flow.inflows, money_out=flow.outflows, net=flow.net,
                        savings_rate=flow.savings_rate, investing_result=investing["result"],
                        keys=(("month", "This month"), ("last", "Last month"), ("ytd", "This year"), ("all", "All time")),
                        since=fmt_date(before), bridge=bridge, gold_change=gold)
