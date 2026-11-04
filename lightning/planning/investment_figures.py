"""Investment figures shared by pages: ownership, lifetime class gain and allocation.

This read model uses Position's holdings value, including balance-only holdings.
It does not substitute the period investment report's value (owed gam'eya policy).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from lightning.core.money import ZERO
from lightning.investments.domain import Position as InvestmentPosition

if TYPE_CHECKING:
    from .position import OwnedHolding, Position

OwnedRow = tuple[InvestmentPosition, Decimal | None, str, str, Decimal, Decimal | None, Decimal]


@dataclass(frozen=True)
class InvestmentBreakdown:
    groups: list[dict]
    horizons: dict[str, Decimal]
    balances: list[tuple[str, OwnedHolding]]
    total: Decimal


def _owned_split(split, units, quantity, gain) -> dict:
    """Your share of a foreign holding's price part and FX part; the FX part takes the rounding so the two add to
    the gain shown."""
    if split is None or gain is None or not quantity:
        return {}
    share = units / quantity
    price_part = (split[0] * share).quantize(Decimal("0.01"))
    return {"price_part": price_part, "fx_part": gain - price_part}



def _native_cost(found, quantity) -> dict:
    """Currency and average cost per unit in that currency, for a holding priced in a foreign currency."""
    if not found or not quantity:
        return {"currency": None, "average_cost_native": None}
    currency, cost_native = found
    return {"currency": currency, "average_cost_native": cost_native / quantity}



def investment_breakdown(owned_rows: list[OwnedRow], position: Position, report: dict,
                         base_currency: str) -> InvestmentBreakdown:
    """Build owned lifetime gains and allocation from the same values as Overview.

    Presentation can group these rows without recomputing financial figures.
    Missing values, partial custody, closed-sale gains and balance-only assets
    retain their existing policies; no database or plan writes occur.
    """
    # Assets known only by their balance (a share of a flat, cash left in an older deposit account) are
    # holdings too (owner decision 2026-10-04): the table lists every part of Holdings value.
    traded = {(h.account_id, h.asset_id) for h, *_ in owned_rows}
    balances = [(cls.name, item) for cls in position.classes for item in cls.items
                if (item.account_id, item.asset_id) not in traded and item.value]
    holdings_total = position.holdings_value  # the weights' base: Holdings value, as the Overview shows it
    # A balance-only asset has no horizon of its own yet: it is Unassigned, so the horizon split adds up
    # to Holdings value (audit 2026-10-05 #13: the flat was left out).
    horizons = defaultdict(lambda: ZERO)
    for _, yours, _, horizon, *_ in owned_rows:
        horizons[horizon] += yours or ZERO
    for _, item in balances:
        horizons["Unassigned"] += item.value
    # A holding in another currency: its gain from the price and from the exchange rate (Overview #16).
    splits = {(r["account_id"], r["asset_id"]): (r["price_part"], r["fx_part"]) for r in report.get("holdings", [])
              if r.get("price_part") is not None and "account_id" in r}
    # Price and average cost of a foreign holding are shown in its own currency (audit 2026-10-15).
    native = {(r["account_id"], r["asset_id"]): (r["currency"], r["cost_native"]) for r in report.get("holdings", [])
              if "account_id" in r and r.get("currency") and r["currency"] != base_currency}
    groups: dict[str, dict] = {}
    for h, yours, bucket, horizon, capital, unrealized, units in owned_rows:
        name = h.asset_class.split(" › ")[-1]
        g = groups.setdefault(name, {"name": name, "value": ZERO, "cost": ZERO, "gain": ZERO, "invested": ZERO, "rows": []})
        g["value"] += yours or ZERO
        g["cost"] += capital
        result = h.owned_result(units, yours, capital)
        g["gain"] += result["gain"] or ZERO
        g["invested"] += result["invested"]
        g["rows"].append({"h": h, "kind": name, "units": units, "average_cost": capital / units if units else None, "cost": capital,
                          "price": h.price, "value": yours, **result,
                          "xirr": h.xirr * 100 if h.xirr is not None and units == h.quantity else None,
                          "display_return": h.display_return if units == h.quantity else None,
                          "horizon": horizon, "weight": (yours or ZERO) / holdings_total * 100 if holdings_total else ZERO,
                          **_native_cost(native.get((h.account_id, h.asset_id)), h.quantity),
                          **_owned_split(splits.get((h.account_id, h.asset_id)), units, h.quantity, unrealized)})
    for name, item in balances:
        g = groups.setdefault(name, {"name": name, "value": ZERO, "cost": ZERO, "gain": ZERO, "invested": ZERO, "rows": []})
        g["value"] += item.value
        g["cost"] += item.value
        g["invested"] += item.value  # balance-only holdings still belong in the combined return's base
        g["rows"].append({"h": None, "kind": name, "balance": True, "name": item.account, "account_id": item.account_id,
                          "asset_id": item.asset_id,
                          "value": item.value, "cost": item.value, "gain": ZERO,
                          "weight": item.value / holdings_total * 100 if holdings_total else ZERO})
    for g in groups.values():
        g["rows"].sort(key=lambda r: (-(r["value"] or ZERO), (r["h"].asset_name if r["h"] else r["name"]).casefold()))
        g["weight"] = g["value"] / holdings_total * 100 if holdings_total else ZERO
        g["gain_pct"] = g["gain"] / g["invested"] * 100 if g["invested"] else None
    holding_groups = sorted(groups.values(), key=lambda g: (-g["value"], g["name"].casefold()))
    return InvestmentBreakdown(holding_groups, horizons, balances, holdings_total)
