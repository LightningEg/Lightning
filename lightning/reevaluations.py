"""Monthly investment and foreign-cash checkpoints with linked journal entries."""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from lightning.accounts.service import AccountService
from lightning.core.dates import fmt_date, now_iso, parse_date, today
from lightning.core.errors import ValidationError
from lightning.core.ledger import PostingLine
from lightning.core.money import ONE, ZERO, from_e6, to_e6
from lightning.core.refs import DocType
from lightning.database.connection import Database
from lightning.reporting.service import ReportingService
from lightning.transactions.domain import TxnSource, TxnStatus
from lightning.transactions.service import TransactionService


class ReevaluationService:
    def __init__(self, db: Database, accounts: AccountService, transactions: TransactionService,
                 reporting: ReportingService):
        self.db, self.accounts, self.transactions, self.reporting = db, accounts, transactions, reporting

    def process_due(self, fetch_price=None) -> int:
        """Record every elapsed month-end in chronological order; incomplete periods await user prices."""
        first = self.db.scalar(
            "SELECT MIN(day) FROM ("
            "SELECT MIN(le.date) AS day FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
            "JOIN financial_assets a ON a.id=le.asset_id WHERE t.status='POSTED' "
            "AND (a.is_cash=0 OR (a.is_cash=1 AND a.currency<>?)) "
            "UNION ALL SELECT MIN(date) AS day FROM reevaluation_periods"
            ") WHERE day IS NOT NULL", (self.reporting.base_currency,))
        if not first:
            return 0
        first_day = parse_date(first)
        last_day = today()
        cursor = date(first_day.year, first_day.month, 1)
        events: set[tuple[str, str]] = set()
        while cursor <= last_day:
            month_end = date(cursor.year, cursor.month, calendar.monthrange(cursor.year, cursor.month)[1])
            if month_end <= last_day:
                events.add((fmt_date(month_end), "MONTH_END"))
            cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
        # Revisit every existing checkpoint as well as newly due month ends. This
        # matters when the last trade is voided: there are no current holdings to
        # seed the date range, but old VAL journals still need to be voided.
        events.update((row["date"], row["reason"]) for row in self.db.all(
            "SELECT date,reason FROM reevaluation_periods"))
        completed = 0
        for day, reason in sorted(events, key=lambda item: (item[0], item[1] != "SALE")):
            if reason == "MONTH_END" and self.db.scalar(
                    "SELECT 1 FROM reevaluation_periods p WHERE date=? AND reason='SALE' AND status='POSTED' "
                    "AND EXISTS (SELECT 1 FROM reevaluation_entries e WHERE e.period_id=p.id)", (day,)):
                continue
            focus = forced = None
            if reason == "SALE":
                sale_rows = self.db.all(
                    "SELECT le.account_id,le.asset_id,le.owner_id,le.unit_price_e6 FROM ledger_entries le "
                    "JOIN transactions t ON t.id=le.transaction_id JOIN financial_assets a ON a.id=le.asset_id "
                    "WHERE t.status='POSTED' AND t.type='SEL' AND t.date=? AND a.is_cash=0 AND le.quantity_e6<0",
                    (day,))
                focus = {(r["account_id"], r["asset_id"], r["owner_id"]) for r in sale_rows}
                forced = {(r["asset_id"], r["owner_id"]): from_e6(r["unit_price_e6"]) for r in sale_rows}
            if self.process_date(day, reason, fetch_price=fetch_price, focus=focus, forced_prices=forced):
                completed += 1
            else:
                break
        return completed

    def process_sale(self, day: str, account_id: int, asset_id: int, price: Decimal,
                     owner_id: int | None = None) -> bool:
        """Force an asset checkpoint at its sale price on the sale date."""
        if self.db.scalar("SELECT 1 FROM reevaluation_periods WHERE status='PENDING' AND date<? LIMIT 1", (day,)):
            with self.db.transaction():
                self.db.execute("INSERT INTO reevaluation_periods(date,reason,status,created_at) "
                                "VALUES(?,'SALE','PENDING',?) ON CONFLICT(date,reason) DO NOTHING",
                                (day, now_iso()))
            return False
        return self.process_date(day, "SALE", fetch_price=None, focus={(account_id, asset_id, owner_id)},
                                 forced_prices={(asset_id, owner_id): price})

    def process_date(self, day: str | date, reason: str, fetch_price=None,
                     focus: set[tuple[int, int, int | None]] | None = None,
                     forced_prices: dict[tuple[int, int | None], Decimal] | None = None) -> bool:
        day = fmt_date(parse_date(day))
        if reason not in {"MONTH_END", "SALE"}:
            raise ValidationError("Unknown reevaluation checkpoint.")
        with self.db.transaction():
            self.db.execute("INSERT INTO reevaluation_periods(date,reason,status,created_at) VALUES(?,?, 'PENDING',?) "
                            "ON CONFLICT(date,reason) DO NOTHING", (day, reason, now_iso()))
            period_id = self.db.scalar("SELECT id FROM reevaluation_periods WHERE date=? AND reason=?", (day, reason))
            source_hash = self._source_hash(day, reason, forced_prices)
            status = self.db.scalar("SELECT status FROM reevaluation_periods WHERE id=?", (period_id,))
            saved_hash = self.db.scalar("SELECT source_hash FROM reevaluation_periods WHERE id=?", (period_id,))
            if status == "POSTED" and saved_hash == source_hash:
                return True
            if status == "POSTED":
                linked = self.db.all("SELECT transaction_id FROM reevaluation_account_posts WHERE period_id=?",
                                     (period_id,))
                for row in linked:
                    txn_id = int(row["transaction_id"])
                    self.transactions.repo.set_status(txn_id, TxnStatus.VOID)
                    self.transactions.audit.record("transaction", txn_id, "void",
                                                   f"Rebuilt changed reevaluation checkpoint {day}")
                # Keep the original link for a manually suppressed account so
                # restoring its journal can re-enable this checkpoint later.
                self.db.execute(
                    "DELETE FROM reevaluation_account_posts WHERE period_id=? AND account_id NOT IN ("
                    "SELECT account_id FROM reevaluation_suppressed_accounts WHERE period_id=?)",
                    (period_id, period_id))
                self.db.execute("UPDATE reevaluation_periods SET status='PENDING' WHERE id=?", (period_id,))
            self.db.execute("DELETE FROM reevaluation_entries WHERE period_id=?", (period_id,))
            rows = self.db.all("SELECT le.account_id,le.asset_id,le.owner_id,SUM(le.quantity_e6) quantity_e6 "
                               "FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
                               "JOIN financial_assets a ON a.id=le.asset_id "
                               "WHERE t.status='POSTED' AND le.date<=? AND "
                               "(a.is_cash=0 OR (a.is_cash=1 AND a.currency<>?)) "
                               "GROUP BY le.account_id,le.asset_id,le.owner_id HAVING SUM(le.quantity_e6)<>0",
                               (day, self.reporting.base_currency))
            positions = {(r["account_id"], r["asset_id"], r["owner_id"]): int(r["quantity_e6"]) for r in rows}
            if focus is not None:
                for key in focus:
                    positions.setdefault(key, 0)
                positions = {k: v for k, v in positions.items() if k in focus}
            incomplete = False
            account_returns: dict[tuple[int, int | None], Decimal] = {}
            certificate_returns: dict[tuple[int, int, int | None], Decimal] = {}
            for (account_id, asset_id, owner_id), units_e6 in sorted(
                    positions.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or 0)):
                asset = self.reporting.assets.get_asset(asset_id)
                forced = (forced_prices or {}).get((asset_id, owner_id))
                found = (ONE, "FX") if asset.is_cash else (
                    (forced, "TRADE") if forced is not None else self._price(asset_id, day))
                if found is None and fetch_price:
                    found = fetch_price(asset, day)
                    if found:
                        price, source = found
                        self.reporting.assets.set_price(asset_id, day, price, source=source)
                if not found:
                    incomplete = True
                    self.db.execute(
                        "INSERT INTO reevaluation_entries(period_id,account_id,asset_id,owner_id,units_e6,currency,needs_price) "
                        "VALUES(?,?,?,?,?,?,1)",
                        (period_id, account_id, asset_id, owner_id, units_e6, asset.currency))
                    continue
                price, source = found
                units = from_e6(units_e6)
                if asset.is_cash or forced is not None:
                    fx = self.reporting.valuer._fx(asset.currency, day)
                    value = (units * price * fx).quantize(Decimal("0.01")) if fx is not None else None
                else:
                    value = self.reporting.value_of(asset_id, units, day).value
                    if value is not None:
                        value = value.quantize(Decimal("0.01"))
                if value is None:
                    incomplete = True
                    self.db.execute(
                        "INSERT INTO reevaluation_entries(period_id,account_id,asset_id,owner_id,units_e6,price_e6,currency,"
                        "price_source,needs_price) VALUES(?,?,?,?,?,?,?,?,1)",
                        (period_id, account_id, asset_id, owner_id, units_e6, to_e6(price), asset.currency, source))
                    continue
                prior = self.db.one(
                    "SELECT e.value_base_e6,p.date FROM reevaluation_entries e JOIN reevaluation_periods p "
                    "ON p.id=e.period_id WHERE e.account_id=? AND e.asset_id=? AND e.owner_id IS ? "
                    "AND p.date<? AND e.needs_price=0 AND NOT EXISTS ("
                    "SELECT 1 FROM reevaluation_suppressed_accounts s WHERE s.period_id=p.id AND s.account_id=e.account_id) "
                    "ORDER BY p.date DESC,p.id DESC LIMIT 1",
                    (account_id, asset_id, owner_id, day))
                flow_start = fmt_date(parse_date(prior["date"]) + timedelta(days=1)) if prior else None
                flow_sql = "SELECT COALESCE(SUM(amount_base_e6),0) FROM ledger_entries le JOIN transactions t " \
                           "ON t.id=le.transaction_id WHERE t.status='POSTED' AND le.account_id=? AND le.asset_id=? " \
                           "AND le.date<=?"
                if asset.is_cash:
                    flow_sql += " AND t.type<>'VAL'"
                flow_sql += " AND le.owner_id IS ?"
                params: list = [account_id, asset_id, day, owner_id]
                if flow_start:
                    flow_sql += " AND le.date>=?"
                    params.append(flow_start)
                flows = from_e6(self.db.scalar(flow_sql, tuple(params)) or 0)
                prior_value = from_e6(prior["value_base_e6"]) if prior else ZERO
                ret = (value - prior_value - flows).quantize(Decimal("0.01"))
                self.db.execute(
                    "INSERT INTO reevaluation_entries(period_id,account_id,asset_id,owner_id,units_e6,price_e6,currency,"
                    "value_base_e6,return_base_e6,price_source,needs_price) VALUES(?,?,?,?,?,?,?,?,?,?,0)",
                    (period_id, account_id, asset_id, owner_id, units_e6, to_e6(price), asset.currency,
                     to_e6(value), to_e6(ret), source))
                owner_key = (account_id, owner_id)
                account_returns[owner_key] = account_returns.get(owner_key, ZERO) + ret
                if self.accounts.get(account_id).account_type.value == "DEPOSIT":
                    certificate_key = (account_id, asset_id, owner_id)
                    certificate_returns[certificate_key] = certificate_returns.get(certificate_key, ZERO) + ret
            if incomplete:
                return False
            for account_id in sorted({key[0] for key in account_returns}):
                if self.db.scalar("SELECT 1 FROM reevaluation_suppressed_accounts WHERE period_id=? AND account_id=?",
                                  (period_id, account_id)):
                    continue
                account = self.accounts.get(account_id)
                cash_asset = self.reporting.assets.cash_asset(account.currency)
                fx = self.reporting.valuer._fx(account.currency, day)
                if fx is None:
                    return False
                if self.accounts.get(account_id).account_type.value == "DEPOSIT":
                    owner_lines = [PostingLine.revaluation(
                        row_account, asset_id, (amount_base / fx).quantize(Decimal("0.000001")), fx,
                        f"Investment revaluation · {reason.lower()}", owner_id=owner_id, is_cash=False)
                        for (row_account, asset_id, owner_id), amount_base in sorted(
                            certificate_returns.items(), key=lambda item: (item[0][1], item[0][2] or 0))
                        if row_account == account_id]
                else:
                    owner_lines = [PostingLine.revaluation(
                        account_id, cash_asset.id, (amount_base / fx).quantize(Decimal("0.000001")), fx,
                        f"Investment revaluation · {reason.lower()}", owner_id=owner_id)
                        for (row_account, owner_id), amount_base in sorted(
                            account_returns.items(), key=lambda item: (item[0][0], item[0][1] or 0))
                        if row_account == account_id]
                amount_base = sum((value for (row_account, _), value in account_returns.items()
                                   if row_account == account_id), ZERO)
                journal = self.transactions.post(
                    DocType.VAL, day, owner_lines,
                    description="Investment revaluation", counterparty="", notes=f"System-generated · {reason}",
                    source=TxnSource.SYSTEM)
                self.db.execute("INSERT INTO reevaluation_account_posts(period_id,account_id,transaction_id,"
                                "amount_base_e6) VALUES(?,?,?,?)",
                                (period_id, account_id, journal.id, to_e6(amount_base)))
                self.db.execute("UPDATE reevaluation_entries SET journal_transaction_id=? "
                                "WHERE period_id=? AND account_id=?",
                                (journal.id, period_id, account_id))
            self.db.execute("UPDATE reevaluation_periods SET status='POSTED',source_hash=? WHERE id=?",
                            (source_hash, period_id))
        return True

    def _source_hash(self, day: str, reason: str, forced_prices: dict | None) -> str:
        """Fingerprint posted holdings activity and dated inputs for this checkpoint."""
        activity = [tuple(row) for row in self.db.all(
            "SELECT le.date,le.account_id,le.asset_id,le.owner_id,le.quantity_e6,le.unit_price_e6,le.amount_base_e6,"
            "t.type,t.status FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
            "JOIN financial_assets a ON a.id=le.asset_id WHERE "
            "(a.is_cash=0 OR (a.is_cash=1 AND a.currency<>? AND t.type<>'VAL')) AND le.date<=? "
            "ORDER BY le.date,le.account_id,le.asset_id,t.id,le.line_no",
            (self.reporting.base_currency, day))]
        prices = [tuple(row) for row in self.db.all(
            "SELECT p.asset_id,p.date,p.price_e6,p.currency,p.source FROM price_history p "
            "JOIN financial_assets a ON a.id=p.asset_id WHERE a.is_cash=0 AND p.date<=? "
            "ORDER BY p.asset_id,p.date,p.source", (day,))]
        fx = [tuple(row) for row in self.db.all(
            "SELECT date,base,quote,rate_e6,source FROM fx_rates WHERE date<=? ORDER BY date,base,quote,source",
            (day,))]
        forced = sorted((str(asset_id), str(owner_id), str(price))
                        for (asset_id, owner_id), price in (forced_prices or {}).items())
        physical, manual = [], []
        if self.db.has_table("physical_items"):
            physical = [tuple(row) for row in self.db.all(
                "SELECT p.asset_id,p.account_id,p.item_kind,p.net_gold_grams_e6,p.karat,p.reference_asset_id,a.name "
                "FROM physical_items p JOIN financial_assets a ON a.id=p.asset_id ORDER BY p.asset_id")]
            manual = [tuple(row) for row in self.db.all(
                "SELECT asset_id,date,quantity_e6,total_value_e6 FROM physical_item_valuations "
                "WHERE date<=? ORDER BY asset_id,date,id", (day,))]
        payload = json.dumps([reason, activity, prices, fx, forced, physical, manual],
                             separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _price(self, asset_id: int, day: str):
        if self.db.has_table("physical_items") and self.db.scalar(
                "SELECT 1 FROM physical_items WHERE asset_id=?", (asset_id,)):
            valuation = self.reporting.valuer.value(self.reporting.assets.get_asset(asset_id), Decimal(1), day)
            if valuation.value is None or valuation.source == "COST" or not valuation.price_date:
                return None
            # Physical-item values are explicit dated appraisals, not market
            # quotes; retain the latest recorded appraisal until replaced.
            return valuation.price, valuation.source
        asset = self.reporting.assets.get_asset(asset_id)
        found = self.reporting.valuer._price(asset, day)
        if not found or found[2] == "COST":
            return None
        price, price_date, source = found
        if self.reporting.assets.get_class(asset.asset_class_id).code == "DEPOSIT.CD":
            # A CD has no market quote. Its purchase price remains its principal value until
            # the user enters a new valuation, so it does not need a new price each month.
            return price, source
        if (parse_date(day) - parse_date(price_date)).days > 10:
            return None
        return price, source

    def has_price(self, asset_id: int, day: str) -> bool:
        """Whether a month-end can be valued from saved prices (a price within ten days before it)."""
        return self._price(asset_id, day) is not None

    def pending_prices(self) -> list[dict]:
        return [dict(row) for row in self.db.all(
            "SELECT DISTINCT p.date,e.asset_id,a.name AS asset_name,a.code AS asset_code,e.currency "
            "FROM reevaluation_entries e JOIN reevaluation_periods p ON p.id=e.period_id "
            "JOIN financial_assets a ON a.id=e.asset_id WHERE e.needs_price=1 AND a.is_cash=0 "
            "AND p.status='PENDING' "
            "ORDER BY p.date,a.name")]

    def pending_fx(self) -> list[dict]:
        """Foreign cash checkpoints awaiting a dated conversion rate."""
        return [dict(row) for row in self.db.all(
            "SELECT DISTINCT p.date,e.currency FROM reevaluation_entries e "
            "JOIN reevaluation_periods p ON p.id=e.period_id "
            "JOIN financial_assets a ON a.id=e.asset_id "
            "WHERE e.needs_price=1 AND a.is_cash=1 AND p.status='PENDING' "
            "ORDER BY p.date,e.currency")]

    def history(self, limit: int = 300, entry_ids: set[int] | None = None) -> list[dict]:
        """Visible checkpoints, or an exact selection of checkpoint entry IDs."""
        if entry_ids is not None and not entry_ids:
            return []
        selection = ("WHERE e.id IN (" + ",".join("?" for _ in entry_ids) + ") ") if entry_ids is not None else ""
        rows = self.db.all(
            "SELECT e.id,p.date,p.reason,p.status,e.account_id,a.name AS account_name,e.asset_id,f.name AS asset_name,"
            "e.owner_id,c.name AS owner_name,"
            "e.units_e6,e.price_e6,e.currency,e.value_base_e6,e.return_base_e6,e.price_source,e.needs_price,"
            "e.journal_transaction_id,t.ref FROM reevaluation_entries e "
            "JOIN reevaluation_periods p ON p.id=e.period_id JOIN accounts a ON a.id=e.account_id "
            "JOIN financial_assets f ON f.id=e.asset_id LEFT JOIN counterparties c ON c.id=e.owner_id "
            "LEFT JOIN transactions t ON t.id=e.journal_transaction_id " + selection +
            "ORDER BY p.date DESC,a.name,f.name,e.id LIMIT ?", (*sorted(entry_ids), limit) if entry_ids is not None else (limit,))
        return [dict(row) | {key: (from_e6(row[key]) if row[key] is not None else None)
                             for key in ("units_e6", "price_e6", "value_base_e6", "return_base_e6")}
                for row in rows]

    def history_for_period(self, start: str, end: str,
                           opening_positions: set[tuple[int, int]] | None = None) -> list[dict]:
        """All owned checkpoints in a period plus the last prior checkpoint per opening holding."""
        columns = ("e.id,p.date,p.reason,p.status,e.account_id,a.name AS account_name,e.asset_id,f.name AS asset_name,"
                   "e.owner_id,c.name AS owner_name,e.units_e6,e.price_e6,e.currency,e.value_base_e6,e.return_base_e6,"
                   "e.price_source,e.needs_price,e.journal_transaction_id,t.ref")
        joins = ("FROM reevaluation_entries e JOIN reevaluation_periods p ON p.id=e.period_id "
                 "JOIN accounts a ON a.id=e.account_id JOIN financial_assets f ON f.id=e.asset_id "
                 "LEFT JOIN counterparties c ON c.id=e.owner_id "
                 "LEFT JOIN transactions t ON t.id=e.journal_transaction_id ")
        rows = self.db.all("SELECT " + columns + " " + joins +
                           "WHERE e.owner_id IS NULL AND p.date BETWEEN ? AND ? "
                           "ORDER BY p.date,a.name,f.name,e.id", (start,end))
        context_keys = sorted(opening_positions or set())
        if context_keys:
            context = []
            for offset in range(0, len(context_keys), 300):
                chunk = context_keys[offset:offset + 300]
                values = ",".join("(?,?)" for _ in chunk)
                params = [value for pair in chunk for value in pair] + [start]
                context.extend(self.db.all(
                    "WITH wanted(account_id,asset_id) AS (VALUES " + values + "), ranked AS (SELECT " +
                    columns + ",ROW_NUMBER() OVER (PARTITION BY e.account_id,e.asset_id "
                    "ORDER BY p.date DESC,e.id DESC) AS rn " + joins +
                    "JOIN wanted w ON w.account_id=e.account_id AND w.asset_id=e.asset_id "
                    "WHERE e.owner_id IS NULL AND p.date<?) "
                    "SELECT * FROM ranked WHERE rn=1", tuple(params)))
            context.sort(key=lambda row: (row["date"], row["account_name"], row["asset_name"], row["id"]))
        else:
            context = []
        def convert(row, scope):
            return dict(row) | {key: (from_e6(row[key]) if row[key] is not None else None)
                                for key in ("units_e6", "price_e6", "value_base_e6", "return_base_e6")} | {"scope": scope}
        return ([convert(row, "OPENING_CONTEXT") for row in context]
                + [convert(row, "IN_PERIOD") for row in rows])

    def record_manual_price(self, asset_id: int, day: str, price: Decimal, fetch_price=None) -> int:
        self.reporting.assets.set_price(asset_id, day, price, source="REEVALUATION_MANUAL")
        reference_items = (" OR e.asset_id IN (SELECT asset_id FROM physical_items WHERE reference_asset_id=?)"
                           if self.db.has_table("physical_items") else "")
        params = [asset_id]
        if reference_items:
            params.append(asset_id)
        params.append(day)
        periods = self.db.all("SELECT DISTINCT p.date,p.reason FROM reevaluation_periods p "
                              "JOIN reevaluation_entries e ON e.period_id=p.id WHERE (e.asset_id=?" +
                              reference_items + ") AND p.date>=? ORDER BY p.date,p.id", tuple(params))
        done = 0
        for period in periods:
            done += bool(self.process_date(period["date"], period["reason"], fetch_price))
            if not self.db.scalar("SELECT status FROM reevaluation_periods WHERE date=? AND reason=?",
                                  (period["date"], period["reason"])) == "POSTED":
                break
        return done
