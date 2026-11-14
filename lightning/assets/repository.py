"""SQL for asset_classes and financial_assets. Only this module touches those tables."""

from __future__ import annotations

import sqlite3

from lightning.core.dates import now_iso
from lightning.core.memo import request_cached
from lightning.core.money import from_e6, to_e6
from lightning.database.connection import Database

from .domain import AssetClass, Exposure, FinancialAsset, Liquidity, Price, PriceSource


def _class(row: sqlite3.Row) -> AssetClass:
    return AssetClass(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        parent_id=row["parent_id"],
        sort_order=row["sort_order"],
        active=bool(row["active"]),
    )


def _asset(row: sqlite3.Row) -> FinancialAsset:
    return FinancialAsset(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        asset_class_id=row["asset_class_id"],
        currency=row["currency"],
        unit=row["unit"],
        quantity_decimals=row["quantity_decimals"],
        is_cash=bool(row["is_cash"]),
        exposure=Exposure(row["exposure"]),
        liquidity=Liquidity(row["liquidity"]),
        purity=None if row["purity_e6"] is None else from_e6(row["purity_e6"]),
        isin=row["isin"],
        price_source=PriceSource(row["price_source"]),
        external_symbol=row["external_symbol"],
        active=bool(row["active"]),
        notes=row["notes"],
        mic=row["mic"] if "mic" in row.keys() else None,
        country=row["country"] if "country" in row.keys() else None,
        market_key=row["market_key"] if "market_key" in row.keys() else None,
        counts_as_cash=bool(row["counts_as_cash"]) if "counts_as_cash" in row.keys() else False,
    )


class AssetRepository:
    def __init__(self, db: Database):
        self.db = db

    # asset classes
    def list_classes(self) -> list[AssetClass]:
        return [_class(r) for r in self.db.all("SELECT * FROM asset_classes ORDER BY sort_order, code")]

    def get_class(self, class_id: int) -> AssetClass | None:
        row = self.db.one("SELECT * FROM asset_classes WHERE id = ?", (class_id,))
        return _class(row) if row else None

    @request_cached(deep=True)
    def get_class_by_code(self, code: str) -> AssetClass | None:
        row = self.db.one("SELECT * FROM asset_classes WHERE code = ?", (code,))
        return _class(row) if row else None

    # financial assets
    @request_cached(deep=True)
    def list_assets(self) -> list[FinancialAsset]:
        return [_asset(r) for r in self.db.all("SELECT * FROM financial_assets ORDER BY code")]

    @request_cached(deep=True)
    def get_asset(self, asset_id: int) -> FinancialAsset | None:
        row = self.db.one("SELECT * FROM financial_assets WHERE id = ?", (asset_id,))
        return _asset(row) if row else None

    @request_cached(deep=True)
    def get_asset_by_code(self, code: str) -> FinancialAsset | None:
        row = self.db.one("SELECT * FROM financial_assets WHERE code = ?", (code,))
        return _asset(row) if row else None

    @request_cached(deep=True)
    def get_cash_asset(self, currency: str) -> FinancialAsset | None:
        row = self.db.one(
            "SELECT * FROM financial_assets WHERE is_cash = 1 AND currency = ?", (currency,)
        )
        return _asset(row) if row else None

    def insert_asset(self, a: FinancialAsset) -> int:
        now = now_iso()
        cur = self.db.execute(
            "INSERT INTO financial_assets(code, name, asset_class_id, currency, unit, quantity_decimals, is_cash,"
            " exposure, liquidity, purity_e6, isin, price_source, external_symbol, active, notes, created_at,"
            " updated_at, mic, country, market_key) VALUES (?,?,?,?,?,?,0,?,?,?,?,?,?,1,?,?,?,?,?,?)",
            (a.code, a.name, a.asset_class_id, a.currency, a.unit, a.quantity_decimals, a.exposure.value,
             a.liquidity.value, None if a.purity is None else to_e6(a.purity), a.isin, a.price_source.value,
             a.external_symbol, a.notes, now, now, a.mic, a.country, a.market_key),
        )
        return int(cur.lastrowid)

    def update_asset(self, a: FinancialAsset) -> None:
        self.db.execute(
            "UPDATE financial_assets SET code=?, name=?, asset_class_id=?, exposure=?, isin=?, external_symbol=?, active=?,"
            " notes=?, mic=?, country=?, market_key=?, updated_at=? WHERE id=?",
            (a.code, a.name, a.asset_class_id, a.exposure.value, a.isin, a.external_symbol, int(a.active), a.notes,
             a.mic, a.country, a.market_key, now_iso(), a.id),
        )

    def set_counts_as_cash(self, asset_id: int, counts: bool) -> None:
        self.db.execute("UPDATE financial_assets SET counts_as_cash=?, updated_at=? WHERE id=?",
                        (int(counts), now_iso(), asset_id))

    # prices
    def upsert_price(self, asset_id: int, date: str, price, currency: str, source: str) -> None:
        now = now_iso()
        self.db.execute(
            "INSERT INTO price_history(asset_id, date, price_e6, currency, source, fetched_at, created_at)"
            " VALUES (?,?,?,?,?,?,?) ON CONFLICT(asset_id, date, source) DO UPDATE SET price_e6 = excluded.price_e6,"
            " fetched_at = excluded.fetched_at",
            (asset_id, date, to_e6(price), currency, source, now, now),
        )

    def has_price(self, asset_id: int, date: str) -> bool:
        return self.db.scalar("SELECT 1 FROM price_history WHERE asset_id=? AND date=? LIMIT 1", (asset_id, date)) is not None

    def delete_price(self, asset_id: int, date: str, source: str) -> None:
        self.db.execute("DELETE FROM price_history WHERE asset_id = ? AND date = ? AND source = ?",
                        (asset_id, date, source))

    def prices(self, asset_id: int, limit: int = 50) -> list[Price]:
        rows = self.db.all(
            "SELECT * FROM price_history WHERE asset_id = ? ORDER BY date DESC, source LIMIT ?", (asset_id, limit))
        return [Price(r["asset_id"], r["date"], from_e6(r["price_e6"]), r["currency"], r["source"]) for r in rows]
