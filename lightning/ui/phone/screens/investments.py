"""Investments on the phone (IV-3AY15, report: *Investments page*): the portfolio's value with the month's result, the
holdings (the biggest five, then every one), prices to update, what changed as rows, and Holdings after sale. The same
services the PC page reads; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.core.dates import fmt_date
from lightning.investments.report import explain_period, investment_period

SHOWN = 5
PARTS = (("price", "Price change on what you hold"), ("fx", "Exchange rates"), ("sales", "Gain from sales"),
         ("income", "Income, less tax and fees"))


@dataclass(frozen=True)
class HoldingRow:
    name: str
    account: str
    value: Decimal | None
    gain_pct: Decimal | None     # return since purchase; None when it cannot be known
    href: str


@dataclass(frozen=True)
class InvestmentsScreen:
    value: Decimal                         # the portfolio value the PC and Money show
    result: Decimal | None                 # this month's result; None when a price is missing
    start: str
    end: str
    holdings: tuple[HoldingRow, ...]       # biggest first; all of them
    shown: int                             # how many the page draws (SHOWN, or all when asked)
    prices_missing: int
    changed: tuple[tuple[str, Decimal], ...]   # what changed this month, as (part, amount)
    cash: Decimal | None                   # brokerage cash
    after_sale: Decimal | None


def build(c, day: date, expanded: bool = False) -> InvestmentsScreen:
    start, end = day.replace(day=1), day
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(start), fmt_date(end))
    explain = explain_period(report, fmt_date(start), fmt_date(end))
    position = c.position.at(day)
    rows = []
    for h in report["holdings"]:
        gain = h["unrealized"] / h["cost"] * 100 if h["unrealized"] is not None and h["cost"] else None
        rows.append(HoldingRow(
            name=h["asset"], account=h["account"], value=h["value"], gain_pct=gain,
            href=f"/investments/holding/{h['asset_id']}?account={h['account_id']}&date={fmt_date(end)}&start={fmt_date(start)}"
            if h.get("asset_id") else f"/accounts/{h.get('account_id', '')}".rstrip("/")))
    rows.sort(key=lambda r: (r.value is None, -(r.value or Decimal(0)), r.name.casefold()))
    return InvestmentsScreen(
        value=position.holdings_value, result=report["result"], start=fmt_date(start), end=fmt_date(end),
        holdings=tuple(rows), shown=len(rows) if expanded else SHOWN, prices_missing=len(report["missing"]),
        changed=tuple((label, part["amount"]) for key, label in PARTS for part in explain["parts"]
                      if part["key"] == key and part["amount"]),
        cash=report["investment_cash"], after_sale=position.holdings_after_sale)
