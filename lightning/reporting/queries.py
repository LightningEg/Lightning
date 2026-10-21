"""Read-only SQL for reports.

Reporting owns no tables; it reads the ledger (and later prices/FX) directly for speed.
Only POSTED transactions count. All sums are over exact integer (_e6) columns.
"""

from __future__ import annotations

from lightning.core.memo import request_cached
from lightning.database.connection import Database

POSTED = "JOIN transactions t ON t.id = le.transaction_id AND t.status = 'POSTED'"
CASH_ONLY = "le.asset_id IN (SELECT id FROM financial_assets WHERE is_cash = 1)"


class ReportQueries:
    def __init__(self, db: Database):
        self.db = db

    def holdings(self, as_of: str) -> list[dict]:
        rows = self.db.all(
            f"SELECT le.account_id, le.asset_id, SUM(le.quantity_e6) AS quantity_e6,"
            f" SUM(le.amount_base_e6) AS cost_base_e6"
            f" FROM ledger_entries le {POSTED} WHERE le.date <= ?"
            f" GROUP BY le.account_id, le.asset_id",
            (as_of,),
        )
        return [dict(r) for r in rows]

    def flows_by_holding(self, date_from: str, date_to: str) -> list[dict]:
        rows = self.db.all(
            f"SELECT le.account_id, le.asset_id, SUM(le.quantity_e6) AS quantity_e6,"
            f" SUM(le.amount_base_e6) AS amount_base_e6"
            f" FROM ledger_entries le {POSTED} WHERE le.date BETWEEN ? AND ? AND le.effect<>'REVALUATION'"
            f" GROUP BY le.account_id, le.asset_id",
            (date_from, date_to),
        )
        return [dict(r) for r in rows]

    @request_cached(deep=True)
    def effect_totals(self, date_from: str, date_to: str) -> dict[str, int]:
        rows = self.db.all(
            f"SELECT le.effect, SUM(le.amount_base_e6) AS total"
            f" FROM ledger_entries le {POSTED} WHERE le.date BETWEEN ? AND ?"
            " GROUP BY le.effect",
            (date_from, date_to),
        )
        return {r["effect"]: int(r["total"] or 0) for r in rows}

    @request_cached(deep=True)
    def category_totals(self, date_from: str, date_to: str) -> list[dict]:
        rows = self.db.all(
            f"SELECT le.category_id, le.effect, SUM(le.amount_base_e6) AS total"
            f" FROM ledger_entries le {POSTED}"
            f" WHERE le.date BETWEEN ? AND ? AND le.category_id IS NOT NULL"
            f" AND le.effect IN ('INFLOW','OUTFLOW')"
            " AND COALESCE(le.category_id,0) NOT IN (SELECT id FROM categories WHERE code='EXP.SYSTEM.CUSTODY')"
            " AND le.owner_id IS NULL"
            " GROUP BY le.category_id, le.effect",
            (date_from, date_to),
        )
        return [dict(r) for r in rows]

    @request_cached(deep=True)
    def category_totals_by_date(self, date_from: str, date_to: str, key_length: int = 10) -> list[dict]:
        """The same totals as category_totals, split by day (key_length 10, yyyy-mm-dd) or month (7)."""
        rows = self.db.all(
            f"SELECT substr(le.date, 1, ?) AS key, le.category_id, le.effect, SUM(le.amount_base_e6) AS total"
            f" FROM ledger_entries le {POSTED}"
            f" WHERE le.date BETWEEN ? AND ? AND le.category_id IS NOT NULL"
            f" AND le.effect IN ('INFLOW','OUTFLOW')"
            " AND COALESCE(le.category_id,0) NOT IN (SELECT id FROM categories WHERE code='EXP.SYSTEM.CUSTODY')"
            " AND le.owner_id IS NULL"
            " GROUP BY key, le.category_id, le.effect",
            (key_length, date_from, date_to),
        )
        return [dict(r) for r in rows]

    def spending_lines(self, date_from: str, date_to: str) -> list[dict]:
        """Categorised money in and out lines with their transaction, account and counterparty: the
        same lines as category_totals, one row per line."""
        rows = self.db.all(
            f"SELECT le.transaction_id, le.date, le.account_id, le.category_id, le.effect, le.amount_base_e6 AS amount,"
            f" t.ref, t.counterparty, t.counterparty_id, t.description"
            f" FROM ledger_entries le {POSTED}"
            f" WHERE le.date BETWEEN ? AND ? AND le.category_id IS NOT NULL"
            f" AND le.effect IN ('INFLOW','OUTFLOW')"
            " AND COALESCE(le.category_id,0) NOT IN (SELECT id FROM categories WHERE code='EXP.SYSTEM.CUSTODY')"
            " AND le.owner_id IS NULL",
            (date_from, date_to),
        )
        return [dict(r) for r in rows]

    def ai_analysis_lines(self, date_from: str, date_to: str) -> list[dict]:
        """Owned posted ledger lines for a local analysis workbook, without pagination."""
        rows = self.db.all(
            "SELECT le.transaction_id,le.line_no,le.date,le.account_id,a.code AS account_code,a.name AS account_name,"
            "a.currency AS account_currency,le.asset_id,f.code AS asset_code,f.name AS asset_name,f.currency AS currency,"
            "t.ref,t.type,t.description,t.counterparty,t.notes,le.category_id,c.code AS category_code,"
            "c.name AS category_name,c.direction,c.income_class,c.family,le.effect,le.quantity_e6,"
            "le.unit_price_e6,le.amount_e6,le.amount_base_e6,le.fx_rate_e6,le.memo,le.owner_id,"
            "EXISTS(SELECT 1 FROM ledger_entries custody JOIN categories cc ON cc.id=custody.category_id "
            "WHERE custody.transaction_id=t.id AND cc.code='EXP.SYSTEM.CUSTODY' AND custody.effect='INFLOW') "
            "AS has_custody_entry "
            "FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id AND t.status='POSTED' "
            "JOIN accounts a ON a.id=le.account_id JOIN financial_assets f ON f.id=le.asset_id "
            "LEFT JOIN categories c ON c.id=le.category_id "
            "WHERE le.date BETWEEN ? AND ? AND le.owner_id IS NULL "
            "ORDER BY le.date,t.id,le.line_no", (date_from,date_to))
        return [dict(row) for row in rows]

    def ai_analysis_counts(self, date_from: str, date_to: str) -> tuple[int, int, set[int]]:
        row = self.db.one(
            "SELECT COUNT(*) AS lines,COUNT(DISTINCT t.id) AS transactions "
            "FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id AND t.status='POSTED' "
            "WHERE le.date BETWEEN ? AND ? AND le.owner_id IS NULL", (date_from,date_to))
        category_ids = {int(item["category_id"]) for item in self.db.all(
            "SELECT DISTINCT le.category_id FROM ledger_entries le JOIN transactions t "
            "ON t.id=le.transaction_id AND t.status='POSTED' WHERE le.date BETWEEN ? AND ? "
            "AND le.owner_id IS NULL AND le.category_id IS NOT NULL", (date_from,date_to))}
        return int(row["transactions"] or 0), int(row["lines"] or 0), category_ids

    def account_quantity(self, account_id: int, as_of: str | None = None, before: str | None = None) -> int:
        sql = f"SELECT SUM(le.quantity_e6) FROM ledger_entries le {POSTED} WHERE le.account_id = ? AND {CASH_ONLY}"
        params: list = [account_id]
        if as_of:
            sql += " AND le.date <= ?"
            params.append(as_of)
        if before:
            sql += " AND le.date < ?"
            params.append(before)
        return int(self.db.scalar(sql, tuple(params)) or 0)

    def category_totals_for(self, txn_ids: list[int]) -> list[dict]:
        """The same totals as category_totals, for the given transactions instead of a date range."""
        rows: list[dict] = []
        for at in range(0, len(txn_ids), 500):  # SQLite allows a limited number of parameters
            chunk = txn_ids[at:at + 500]
            rows += [dict(r) for r in self.db.all(
                f"SELECT le.category_id, le.effect, SUM(le.amount_base_e6) AS total"
                f" FROM ledger_entries le {POSTED}"
                f" WHERE le.transaction_id IN ({','.join('?' * len(chunk))}) AND le.category_id IS NOT NULL"
                f" AND le.effect IN ('INFLOW','OUTFLOW')"
                " AND COALESCE(le.category_id,0) NOT IN (SELECT id FROM categories WHERE code='EXP.SYSTEM.CUSTODY')"
                " AND le.owner_id IS NULL"
                " GROUP BY le.category_id, le.effect", tuple(chunk))]
        return rows

    def category_transaction_ids(self, category_ids: set[int]) -> set[int]:
        if not category_ids:
            return set()
        marks = ",".join("?" for _ in category_ids)
        return {int(row["id"]) for row in self.db.all(
            f"SELECT DISTINCT t.id FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            f"WHERE t.status='POSTED' AND le.category_id IN ({marks})", tuple(sorted(category_ids)))}

    @staticmethod
    def _statement_filter(account_id: int | None, date_from: str, date_to: str) -> tuple[str, list]:
        where = f"le.date BETWEEN ? AND ? AND {CASH_ONLY}"
        params: list = [date_from, date_to]
        if account_id is not None:
            where = "le.account_id = ? AND " + where
            params.insert(0, account_id)
        return where, params

    # One register row per transaction, account and date, oldest first. The account breaks ties so
    # the two rows of a transfer keep one order, and a page boundary never repeats or skips one.
    _STATEMENT_GROUP = " GROUP BY le.date,le.account_id,t.id ORDER BY le.date, t.id, le.account_id"

    def statement_lines(self, account_id: int | None, date_from: str, date_to: str,
                        limit: int = -1, offset: int = 0) -> list[dict]:
        """Posted cash lines for one account (or every account when account_id is None) — the register.
        ``limit``/``offset`` select a slice of the rows, oldest first."""
        where, params = self._statement_filter(account_id, date_from, date_to)
        rows = self.db.all(
            f"SELECT le.date, le.account_id, SUM(le.quantity_e6) AS quantity_e6, SUM(le.amount_e6) AS amount_e6,"
            f" SUM(le.amount_base_e6) AS amount_base_e6,"
            f" MAX(le.effect) AS effect, CASE WHEN COUNT(*)=1 THEN MAX(le.category_id) END AS category_id,"
            f" CASE WHEN COUNT(DISTINCT le.category_id)>1 THEN 'Split · ' || COUNT(DISTINCT le.category_id) || ' categories' ELSE MAX(le.memo) END AS memo,"
            f" t.id AS txn_id, t.ref, t.type, t.description, t.counterparty, t.notes,"
            f" (SELECT o.account_id FROM ledger_entries o WHERE o.transaction_id = t.id"
            f"  AND o.account_id != le.account_id LIMIT 1) AS other_account_id"
            f" FROM ledger_entries le {POSTED}"
            f" WHERE {where}{self._STATEMENT_GROUP} LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [dict(r) for r in rows]

    def _statement_groups(self, account_id: int | None, date_from: str, date_to: str) -> tuple[str, list]:
        where, params = self._statement_filter(account_id, date_from, date_to)
        return (f"SELECT SUM(le.quantity_e6) AS q FROM ledger_entries le {POSTED}"
                f" WHERE {where}{self._STATEMENT_GROUP}"), params

    def statement_count(self, account_id: int | None, date_from: str, date_to: str) -> int:
        """How many register rows statement_lines would return."""
        grouped, params = self._statement_groups(account_id, date_from, date_to)
        return int(self.db.scalar(f"SELECT COUNT(*) FROM ({grouped})", tuple(params)))

    def statement_value_updates(self, account_id: int | None, date_from: str, date_to: str) -> int:
        """How many register rows are system revaluations (type VAL)."""
        where, params = self._statement_filter(account_id, date_from, date_to)
        return int(self.db.scalar(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM ledger_entries le {POSTED} WHERE {where} AND t.type='VAL'"
            f"{self._STATEMENT_GROUP})", tuple(params)))

    def statement_movement(self, account_id: int | None, date_from: str, date_to: str, first: int) -> int:
        """The summed movement (_e6) of the oldest ``first`` register rows."""
        grouped, params = self._statement_groups(account_id, date_from, date_to)
        return int(self.db.scalar(f"SELECT COALESCE(SUM(q), 0) FROM ({grouped} LIMIT ?)", (*params, first)))

    @request_cached(deep=True)
    def _prices_of(self, asset_id: int) -> list[dict]:
        """Every price of one asset, newest first, a typed price before an automatic one on the same day.
        One read per asset per request: a page asks for the same asset at a dozen month ends."""
        return [dict(row) for row in self.db.all(
            "SELECT price_e6, currency, date, source FROM price_history WHERE asset_id = ?"
            " ORDER BY date DESC, CASE WHEN source IN ('MANUAL','REEVALUATION_MANUAL') THEN 0 ELSE 1 END",
            (asset_id,))]

    def latest_price(self, asset_id: int, as_of: str) -> dict | None:
        row = next((price for price in self._prices_of(asset_id) if price["date"] <= as_of), None)
        return dict(row) if row else None

    @request_cached(deep=True)
    def _trade_prices_of(self, asset_id: int) -> list[dict]:
        """Every buy and sell price of one asset, newest first; read once per asset per request."""
        return [dict(row) for row in self.db.all(
            f"SELECT le.unit_price_e6 AS price_e6, le.date FROM ledger_entries le {POSTED}"
            " WHERE le.asset_id = ? AND t.type IN ('BUY', 'SEL') ORDER BY le.date DESC, t.id DESC",
            (asset_id,))]

    def latest_trade_price(self, asset_id: int, as_of: str) -> dict | None:
        """The price of the most recent buy or sell on or before the date."""
        row = next((price for price in self._trade_prices_of(asset_id) if price["date"] <= as_of), None)
        return dict(row) if row else None

    @request_cached
    def physical_item(self, asset_id: int) -> dict | None:
        """The gold item behind an asset, if it is one."""
        row = self.db.one("SELECT net_gold_grams_e6,reference_asset_id,account_id,karat FROM physical_items WHERE asset_id=?",
                          (asset_id,))
        return dict(row) if row else None

    @request_cached(deep=True)
    def _item_values_of(self, asset_id: int) -> list[dict]:
        """Every typed value of one item, newest first; read once per item per request."""
        return [dict(row) for row in self.db.all(
            "SELECT date,quantity_e6,total_value_e6 FROM physical_item_valuations WHERE asset_id=? "
            "ORDER BY date DESC,id DESC", (asset_id,))]

    def manual_item_value(self, asset_id: int, as_of: str) -> dict | None:
        row = next((value for value in self._item_values_of(asset_id) if value["date"] <= as_of), None)
        return dict(row) if row else None

    @request_cached
    def asset_purity(self, asset_id: int) -> int | None:
        return self.db.scalar("SELECT purity_e6 FROM financial_assets WHERE id=?", (asset_id,))

    def average_opening_cost(self, asset_id: int, as_of: str) -> dict | None:
        """Cost per unit of holdings entered as already owned — the last resort for a value."""
        row = self.db.one(
            f"SELECT SUM(le.amount_e6) AS amount, SUM(le.quantity_e6) AS qty, MAX(le.date) AS date"
            f" FROM ledger_entries le {POSTED} WHERE le.asset_id = ? AND le.date <= ? AND t.type = 'OPN'",
            (asset_id, as_of),
        )
        return dict(row) if row and row["qty"] else None

    def investment_lines(self, as_of: str, account_id: int | None = None) -> list[dict]:
        """Every posted line of a non-cash asset (and dividend lines), oldest first — for positions."""
        where = "le.date <= ? AND (le.asset_id NOT IN (SELECT id FROM financial_assets WHERE is_cash = 1)" \
                " OR t.type = 'DIV')"
        params: list = [as_of]
        if account_id is not None:
            where += " AND le.account_id = ?"
            params.append(account_id)
        rows = self.db.all(
            f"SELECT le.date, le.account_id, le.asset_id, le.quantity_e6, le.amount_e6, le.amount_base_e6, le.memo, le.owner_id,"
            f" da.asset_id AS dividend_asset_id,"
            f" t.id AS txn_id, t.type, t.ref FROM ledger_entries le {POSTED} "
            f"LEFT JOIN investment_dividend_assets da ON da.transaction_id=t.id WHERE {where}"
            f" ORDER BY le.date, t.id, le.line_no",
            tuple(params),
        )
        return [dict(r) for r in rows]

    def interest_from_banks(self, as_of: str) -> list[dict]:
        """Owned interest received outside investment accounts, with the payer's name, oldest first."""
        return [dict(r) for r in self.db.all(
            f"SELECT le.date, le.amount_base_e6, t.id AS txn_id, cp.name AS payer FROM ledger_entries le {POSTED} "
            "JOIN categories c ON c.id=le.category_id JOIN counterparties cp ON cp.id=t.counterparty_id "
            "JOIN accounts a ON a.id=le.account_id "
            "WHERE c.code='EXP.INVEST.INTEREST' AND le.effect='INFLOW' AND le.owner_id IS NULL AND le.date <= ? "
            "AND a.account_type IN ('BANK','CASH') ORDER BY le.date, t.id", (as_of,))]

    def certificate_lines(self, as_of: str) -> list[dict]:
        """Owned non-cash lines in certificate (DEPOSIT) accounts with the bank's name, oldest first."""
        return [dict(r) for r in self.db.all(
            f"SELECT le.date, le.account_id, le.asset_id, le.amount_base_e6, a.institution FROM ledger_entries le {POSTED} "
            "JOIN accounts a ON a.id=le.account_id JOIN financial_assets fa ON fa.id=le.asset_id "
            "WHERE a.account_type='DEPOSIT' AND fa.is_cash=0 AND le.owner_id IS NULL AND le.date <= ? "
            "ORDER BY le.date, t.id, le.line_no", (as_of,))]

    def opening_total(self, start: str, end: str) -> int:
        """Owned opening balances and existing holdings recorded between two dates, in base e6."""
        return self.db.scalar(f"SELECT COALESCE(SUM(le.amount_base_e6),0) FROM ledger_entries le {POSTED} "
                              "WHERE t.type='OPN' AND le.owner_id IS NULL AND le.date BETWEEN ? AND ?",
                              (start, end)) or 0

    def holdings_opening_total(self, start: str, end: str) -> int:
        """Owned holdings recorded as already owned between two dates, in base e6: non-cash assets, and
        an other-asset account's value (a flat is held as its value, in cash units)."""
        return self.db.scalar(f"SELECT COALESCE(SUM(le.amount_base_e6),0) FROM ledger_entries le {POSTED} "
                              "JOIN financial_assets fa ON fa.id=le.asset_id JOIN accounts a ON a.id=le.account_id "
                              "WHERE t.type='OPN' AND le.owner_id IS NULL AND (fa.is_cash=0 OR a.account_type='OTHER_ASSET') "
                              "AND le.date BETWEEN ? AND ?",
                              (start, end)) or 0

    def opening_by_month(self, start: str, end: str) -> dict[str, int]:
        """Owned opening balances recorded between two dates, per yyyy-mm, in base e6."""
        rows = self.db.all(f"SELECT substr(le.date,1,7) AS month, SUM(le.amount_base_e6) AS amount_e6 "
                           f"FROM ledger_entries le {POSTED} WHERE t.type='OPN' AND le.owner_id IS NULL "
                           "AND le.date BETWEEN ? AND ? GROUP BY month", (start, end))
        return {row["month"]: row["amount_e6"] for row in rows}

    def opening_by_holding(self, start: str, end: str) -> list[dict]:
        """Owned opening balances recorded between two dates, per account and asset, in base e6."""
        return self.db.all(f"SELECT le.account_id, le.asset_id, SUM(le.amount_base_e6) AS amount_e6 "
                           f"FROM ledger_entries le {POSTED} WHERE t.type='OPN' AND le.owner_id IS NULL "
                           "AND le.date BETWEEN ? AND ? GROUP BY le.account_id, le.asset_id", (start, end))

    def has_income_or_spending(self) -> bool:
        return bool(self.db.scalar("SELECT 1 FROM transactions WHERE status='POSTED' AND type IN ('IN','OUT') LIMIT 1"))

    def first_entry_date(self) -> str | None:
        # Opening balances anchor an account; they are not activity for the All time view.
        return self.db.scalar(f"SELECT MIN(le.date) FROM ledger_entries le {POSTED} WHERE t.type<>'OPN'")
