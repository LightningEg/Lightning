"""Turns quantities into base-currency value.

value = quantity x price (on or before the date) x FX rate (asset currency -> base)
- Base-currency cash is always worth its quantity.
- Anything without a price/rate is reported as "unvalued" instead of silently counted as zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.assets.domain import FinancialAsset
from lightning.core.money import ONE, from_e6
from lightning.fx import MISSING_DAYS, Rate, rate_for

from .price_sources import SOURCE_RANK, source_rank  # noqa: F401  (SOURCE_RANK is the written order, re-exported here)
from .queries import ReportQueries


@dataclass
class Valuation:
    value: Decimal | None  # None = missing price or FX rate
    price: Decimal | None
    price_date: str | None
    reason: str = ""
    source: str = ""  # MANUAL (a price you typed) · TRADE (last buy/sell) · COST (what you paid) · CASH
    fx_as_of: str | None = None  # the day of the exchange rate used, when it is older than a week and more


class Valuer:
    def __init__(self, queries: ReportQueries, base_currency: str):
        self.q = queries
        self.base = base_currency
        self._has_items = False

    def _physical_items(self) -> bool:
        # Migrations only ever add this table, so once it exists the answer cannot change.
        if not self._has_items:
            self._has_items = self.q.db.has_table("physical_items")
        return self._has_items

    def value(self, asset: FinancialAsset, quantity: Decimal, as_of: date | str) -> Valuation:
        day = as_of if isinstance(as_of, str) else as_of.isoformat()
        if asset.is_cash:
            price, price_date, source = ONE, None, "CASH"
        else:
            item = self.q.physical_item(asset.id) if self._physical_items() else None
            if item:
                reference = self.reference_price(item["reference_asset_id"], day)
                manual = self.q.manual_item_value(asset.id, day)
                reference_date = reference["date"] if reference else None
                if manual and (reference_date is None or manual["date"] >= reference_date):
                    unit = (Decimal(manual["total_value_e6"]) / Decimal(manual["quantity_e6"]))
                    value = (quantity * unit).quantize(Decimal("0.000001"))
                    return Valuation(value, unit, manual["date"], "", "MANUAL")
                if reference:
                    grams = Decimal(item["net_gold_grams_e6"]) / Decimal(1_000_000)
                    purity = self.q.asset_purity(item["reference_asset_id"])
                    reference_purity = from_e6(purity) if purity is not None else None
                    item_purity = Decimal(item["karat"]) / Decimal(24)
                    purity_adjustment = item_purity if reference_purity == ONE else ONE
                    price = from_e6(reference["price_e6"]) * grams * purity_adjustment
                    fx = self._fx(asset.currency, day)
                    if fx is None:
                        return Valuation(None, price, reference_date,
                                         f"No {asset.currency}/{self.base} rate within {MISSING_DAYS} days before {day}")
                    value = (quantity * price * fx).quantize(Decimal("0.000001"))
                    return Valuation(value, price, reference_date, "", f"{asset.unit} · {reference['source']} reference")
                held_qty = Decimal(0)
                held_cost = Decimal(0)
                cost_date = None
                for line in self.q.investment_lines(day, item["account_id"]):
                    if line["asset_id"] != asset.id:
                        continue
                    line_qty = from_e6(line["quantity_e6"])
                    line_amount = from_e6(line["amount_base_e6"])
                    if line_qty > 0:
                        held_qty += line_qty
                        held_cost += line_amount
                        cost_date = line["date"]
                    elif held_qty > 0:
                        removed = held_cost / held_qty * -line_qty
                        held_cost -= removed
                        held_qty += line_qty
                if held_qty > 0 and held_cost >= 0:
                    unit_cost = held_cost / held_qty
                    return Valuation((quantity * unit_cost).quantize(Decimal("0.000001")), unit_cost,
                                     cost_date, "", "COST")
                return Valuation(None, None, None, f"No gold reference or recorded cost for {asset.name}")
            found = self._gold_price(asset, day) or self._price(asset, day)
            if found is None:
                return Valuation(None, None, None, f"No price for {asset.label} on or before {day}")
            price, price_date, source = found
        rate = self.fx(asset.currency, day)
        if rate is None:
            return Valuation(None, price, price_date, f"No {asset.currency}/{self.base} rate within {MISSING_DAYS} days before {day}")
        return Valuation((quantity * price * rate.rate).quantize(Decimal("0.000001")), price, price_date, "", source,
                         rate.as_of)

    def reference_price(self, reference_id: int, day: str) -> dict | None:
        """A gold reference's price per gram on ``day``. PR-2 (3H2): a karat with no price of its own is worked out
        from another karat's by purity (21K first, then the purest), so an 18K piece is priced as 21K × 18/21;
        a price someone typed for that karat always wins."""
        own = self.q.latest_price(reference_id, day)
        if own:
            return own
        target = self.q.asset_purity(reference_id)
        if not target:
            return None
        for other in self.q.gold_references():
            if other["id"] == reference_id or not other["purity_e6"]:
                continue
            found = self.q.latest_price(other["id"], day)
            if found:
                derived = Decimal(found["price_e6"]) * Decimal(target) / Decimal(other["purity_e6"])
                karat = round(Decimal(other["purity_e6"]) * 24 / Decimal(1_000_000))
                return {"price_e6": int(derived), "date": found["date"], "source": f"{karat}K by purity"}
        return None

    def _gold_price(self, asset: FinancialAsset, day: str) -> tuple[Decimal, str, str] | None:
        """IV-12L: gold held by the gram (a bar, a coin) is valued by the dated karat price, like a jewellery item, not
        by what the last purchase paid; with no karat price at all it falls back to the usual order."""
        if asset.exposure.value != "GOLD" or asset.unit != "gram" or asset.purity is None:
            return None
        found = self.reference_price(asset.id, day)
        return (from_e6(found["price_e6"]), found["date"], found["source"]) if found else None

    def _price(self, asset: FinancialAsset, day: str) -> tuple[Decimal, str, str] | None:
        """Newest price wins; on one day the order is ``SOURCE_RANK`` (a price you typed, then a buy or sell, then the
        market pack and online quotes). Holdings entered as already owned fall back to their cost until a price exists."""
        typed = self.q.latest_price(asset.id, day)
        trade = self.q.latest_trade_price(asset.id, day)
        if typed and (not trade or typed["date"] > trade["date"]
                      or (typed["date"] == trade["date"] and source_rank(typed["source"]) <= source_rank("TRADE"))):
            return from_e6(typed["price_e6"]), typed["date"], typed["source"]
        if trade:
            return from_e6(trade["price_e6"]), trade["date"], "TRADE"
        cost = self.q.average_opening_cost(asset.id, day)
        if cost:
            per_unit = Decimal(cost["amount"]) / Decimal(cost["qty"])  # unrounded: value comes out at exact cost
            return per_unit, cost["date"], "COST"
        return None

    def fx(self, currency: str, day: str) -> Rate | None:
        """The rate (with its day and source) that values `currency` in the base on `day`; None = missing."""
        return rate_for(self.q.db, currency, self.base, day)

    def _fx(self, currency: str, day: str) -> Decimal | None:
        if currency == self.base:
            return ONE
        found = self.fx(currency, day)
        return found.rate if found else None
