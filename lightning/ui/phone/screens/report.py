"""The period report on the phone (IV-3AY11 prerequisite): "How did a period go?". Home is always today, so the
Overview's month, year and all-time reading lives here, behind Money: the change in what you own, money in, out and
kept, the savings rate, and what investing did. Services calculate; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.core.dates import fmt_date, month_of
from lightning.core.errors import LightningError
from lightning.investments.report import investment_period
from lightning.ui.periods import parse_period

KEYS = ("month", "last", "ytd", "all")


@dataclass(frozen=True)
class ReportScreen:
    key: str
    label: str                       # "2026-10", "Year to date", "All time"
    start: str
    end: str
    change: Decimal | None           # change in what you own; None when a valuation is missing
    change_reason: str
    money_in: Decimal
    money_out: Decimal
    net: Decimal
    savings_rate: Decimal | None
    investing_result: Decimal | None  # the period's gain or loss on holdings; None when a price is missing
    keys: tuple[tuple[str, str], ...]


def _period(c, day: date, key: str):
    first = c.reporting.first_activity_date()
    if key == "last":
        before = date(day.year - 1, 12, 1) if day.month == 1 else date(day.year, day.month - 1, 1)
        return parse_period({"period": "month", "month": month_of(before)}, day, first)
    return parse_period({"period": key if key in ("ytd", "all") else "month"}, day, first)


def build(c, day: date, key: str = "month") -> ReportScreen:
    key = key if key in KEYS else "month"
    try:
        period = _period(c, day, key)
    except LightningError:
        key = "month"
        period = _period(c, day, key)
    start, end = period.start, period.end
    flow = c.reporting.cash_flow(start, end)
    change, reason = c.position.change_in_what_you_own(start, end, since_first_record=key == "all")
    investing = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(start), fmt_date(end))
    label = month_of(start) if key in ("month", "last") else period.label
    return ReportScreen(key=key, label=label, start=fmt_date(start), end=fmt_date(end), change=change,
                        change_reason=reason, money_in=flow.inflows, money_out=flow.outflows, net=flow.net,
                        savings_rate=flow.savings_rate, investing_result=investing["result"],
                        keys=(("month", "This month"), ("last", "Last month"), ("ytd", "This year"), ("all", "All time")))
