"""SQL for planned items and their settled payments."""
from __future__ import annotations

from lightning.core.dates import now_iso
from lightning.core.memo import request_cached
from lightning.core.money import from_e6, to_e6
from lightning.database.connection import Database

from .domain import Frequency, PlanKind, PlannedItem, WeekendMove

_COLUMNS = ("kind", "name", "amount_e6", "frequency", "interval_count", "start_date", "end_date",
            "payment_count", "account_id", "category_id", "counterparty_id", "principal_e6", "notes", "weekend_move", "month_day",
            "match_window_days", "match_tolerance_pct")


def _item(row) -> PlannedItem:
    return PlannedItem(
        id=row["id"], kind=PlanKind(row["kind"]), name=row["name"], amount=from_e6(row["amount_e6"]),
        frequency=Frequency(row["frequency"]), interval_count=row["interval_count"],
        start_date=row["start_date"], end_date=row["end_date"], payment_count=row["payment_count"],
        account_id=row["account_id"], category_id=row["category_id"], counterparty_id=row["counterparty_id"],
        principal=from_e6(row["principal_e6"]) if row["principal_e6"] is not None else None,
        active=bool(row["active"]), notes=row["notes"],
        weekend_move=WeekendMove(row["weekend_move"]), month_day=row["month_day"],
        match_window_days=row["match_window_days"], match_tolerance_pct=row["match_tolerance_pct"])


class PlanningRepository:
    def __init__(self, db: Database):
        self.db = db

    @request_cached
    def items(self, active_only: bool = True) -> list[PlannedItem]:
        rows = self.db.all("SELECT * FROM planned_items" + (" WHERE active=1" if active_only else "")
                           + " ORDER BY kind, name COLLATE NOCASE, id")
        return [_item(row) for row in rows]

    def item(self, item_id: int) -> PlannedItem | None:
        row = self.db.one("SELECT * FROM planned_items WHERE id=?", (item_id,))
        return _item(row) if row else None

    def insert(self, values: dict) -> int:
        now = now_iso()
        data = self._row(values)
        cur = self.db.execute(
            f"INSERT INTO planned_items({','.join(_COLUMNS)},created_at,updated_at) "
            f"VALUES({','.join('?' * len(_COLUMNS))},?,?)", (*data, now, now))
        return int(cur.lastrowid)

    def update(self, item_id: int, values: dict) -> None:
        self.db.execute(f"UPDATE planned_items SET {','.join(c + '=?' for c in _COLUMNS)},updated_at=? WHERE id=?",
                        (*self._row(values), now_iso(), item_id))

    def set_amount(self, item_id: int, amount) -> None:
        self.db.execute("UPDATE planned_items SET amount_e6=?, updated_at=? WHERE id=?",
                        (to_e6(amount), now_iso(), item_id))

    def set_start(self, item_id: int, start_date: str, month_day: int | None = None) -> None:
        self.db.execute("UPDATE planned_items SET start_date=?, month_day=COALESCE(?, month_day), updated_at=? "
                        "WHERE id=?", (start_date, month_day, now_iso(), item_id))

    def set_payment_count(self, item_id: int, count: int) -> None:
        self.db.execute("UPDATE planned_items SET payment_count=?,updated_at=? WHERE id=?", (count, now_iso(), item_id))

    def set_active(self, item_id: int, active: bool) -> None:
        self.db.execute("UPDATE planned_items SET active=?,updated_at=? WHERE id=?", (int(active), now_iso(), item_id))

    def delete(self, item_id: int) -> None:
        self.db.execute("DELETE FROM planned_items WHERE id=?", (item_id,))

    def has_payments(self, item_id: int) -> bool:
        return bool(self.db.scalar("SELECT 1 FROM planned_payments WHERE planned_item_id=? "
                                   "UNION ALL SELECT 1 FROM loan_extra_payments WHERE planned_item_id=? LIMIT 1",
                                   (item_id, item_id)))

    @request_cached
    def settled(self) -> dict[tuple[int, str], dict]:
        """Settled payments whose transaction is still posted (a voided payment is unpaid again).

        Read once per request: the Overview's twelve month-end positions each ask for every item's payments."""
        rows = self.db.all(
            "SELECT p.planned_item_id,p.due_date,p.status,p.transaction_id,p.amount_e6,t.date AS transaction_date FROM planned_payments p "
            "LEFT JOIN transactions t ON t.id=p.transaction_id "
            "WHERE p.status='SKIPPED' OR t.status='POSTED'")
        return {(row["planned_item_id"], row["due_date"]): dict(row) for row in rows}

    def is_settled(self, item_id: int, due_date: str) -> bool:
        """Read fresh (not per request): whether that due date is already paid by a posted transaction or skipped."""
        return bool(self.db.scalar(
            "SELECT 1 FROM planned_payments p LEFT JOIN transactions t ON t.id=p.transaction_id "
            "WHERE p.planned_item_id=? AND p.due_date=? AND (p.status='SKIPPED' OR t.status='POSTED')",
            (item_id, due_date)))

    def settle(self, item_id: int, due_date: str, status: str, transaction_id: int | None, amount) -> None:
        self.db.execute("DELETE FROM planned_payments WHERE planned_item_id=? AND due_date=?", (item_id, due_date))
        self.db.execute(
            "INSERT INTO planned_payments(planned_item_id,due_date,status,transaction_id,amount_e6,created_at) "
            "VALUES(?,?,?,?,?,?)", (item_id, due_date, status, transaction_id, to_e6(amount), now_iso()))

    def unsettle(self, item_id: int, due_date: str) -> None:
        self.db.execute("DELETE FROM planned_payments WHERE planned_item_id=? AND due_date=?", (item_id, due_date))

    def linked_transaction_ids(self) -> set[int]:
        return {int(r["transaction_id"]) for r in self.db.all(
            "SELECT transaction_id FROM planned_payments WHERE transaction_id IS NOT NULL "
            "UNION SELECT transaction_id FROM loan_extra_payments")}

    @request_cached
    def installment_terms(self) -> dict[int, dict]:
        return {row["planned_item_id"]: dict(row) for row in self.db.all("SELECT * FROM installment_purchases")}

    @request_cached
    def extra_payments(self, on: str) -> list[dict]:
        return [dict(row) for row in self.db.all(
            "SELECT p.*,t.date FROM loan_extra_payments p JOIN transactions t ON t.id=p.transaction_id "
            "WHERE t.status='POSTED' AND t.date<=? ORDER BY t.date,p.id", (on,))]

    def add_extra_payment(self, item_id, transaction_id, principal, fee, due_date=None):
        self.db.execute("INSERT INTO loan_extra_payments(planned_item_id,transaction_id,principal_e6,fee_e6,due_date,created_at) "
                        "VALUES (?,?,?,?,?,?)", (item_id, transaction_id, to_e6(principal), to_e6(fee), due_date, now_iso()))

    def add_installment_terms(self, item_id, price, fee, count):
        self.db.execute("INSERT INTO installment_purchases VALUES (?,?,?,?)", (item_id, to_e6(price), to_e6(fee), count))

    def candidates(self, incoming: bool, account_id: int | None, category_id: int | None,
                   counterparty_id: int | None, date_from: str, date_to: str, currency: str,
                   require_all_identity: bool = False) -> list[dict]:
        """Posted, owned money-in or money-out transactions that could settle a payment."""
        effect = "INFLOW" if incoming else "OUTFLOW"
        where = ["t.status='POSTED'", "l.effect=?", "l.owner_id IS NULL", "t.date BETWEEN ? AND ?"]
        where.append("l.asset_id IN (SELECT id FROM financial_assets WHERE is_cash=1)")
        where.append("(t.type='IN' AND l.quantity_e6>0)" if incoming else
                     "((t.type='OUT' OR (t.type='ADJ' AND t.description LIKE 'Ownership: expense paid by %')) AND l.quantity_e6<0)")
        params: list = [effect, date_from, date_to]
        if account_id:
            where.append("l.account_id=?"); params.append(account_id)
        match = []
        if counterparty_id:
            match.append("t.counterparty_id=?"); params.append(counterparty_id)
        if category_id:
            match.append("EXISTS (SELECT 1 FROM ledger_entries m WHERE m.transaction_id=t.id "
                         "AND m.effect=l.effect AND m.owner_id IS NULL AND m.category_id=?)")
            params.append(category_id)
        if match:
            where.append("(" + (" AND " if require_all_identity and len(match) > 1 else " OR ").join(match) + ")")
        where.append("a.currency=?")
        params.append(currency)
        rows = self.db.all(
            "SELECT t.id,t.ref,t.date,t.counterparty,t.counterparty_id,GROUP_CONCAT(l.category_id) category_ids,"
            "SUM(ABS(l.quantity_e6)) amount_e6 FROM transactions t "
            "JOIN ledger_entries l ON l.transaction_id=t.id JOIN accounts a ON a.id=l.account_id WHERE " + " AND ".join(where) +
            " GROUP BY t.id ORDER BY t.date,t.id", tuple(params))
        return [dict(row) | {"amount": from_e6(row["amount_e6"]),
                             "category_ids": {int(x) for x in (row["category_ids"] or "").split(",") if x}}
                for row in rows]

    def payment_transaction(self, transaction_id: int, incoming: bool, account_id: int | None,
                            category_id: int | None, counterparty_id: int | None, currency: str) -> dict | None:
        """Read a posted, owned transaction that is valid for an explicit payment link."""
        effect = "INFLOW" if incoming else "OUTFLOW"
        doc_type = "IN" if incoming else "OUT"
        where = ["t.id=?", "t.status='POSTED'", "l.effect=?", "l.owner_id IS NULL"]
        where.append("l.asset_id IN (SELECT id FROM financial_assets WHERE is_cash=1)")
        where.append("l.quantity_e6>0" if incoming else "l.quantity_e6<0")
        params: list = [transaction_id, effect]
        if incoming:
            where.append("t.type='IN'")
        else:
            # An externally paid expense is represented by an ADJ whose owned
            # expense line is still a real budget/planned-payment outflow.
            where.append("(t.type='OUT' OR (t.type='ADJ' AND t.description LIKE 'Ownership: expense paid by %'))")
        if account_id:
            where.append("l.account_id=?")
            params.append(account_id)
        where.append("a.currency=?")
        params.append(currency)
        identity = []
        if counterparty_id:
            identity.append("t.counterparty_id=?")
            params.append(counterparty_id)
        if category_id:
            identity.append("EXISTS (SELECT 1 FROM ledger_entries m WHERE m.transaction_id=t.id "
                            "AND m.effect=l.effect AND m.owner_id IS NULL AND m.category_id=?)")
            params.append(category_id)
        if not identity:
            return None
        where.append("(" + " OR ".join(identity) + ")")
        row = self.db.one(
            "SELECT t.id,t.date,SUM(ABS(l.quantity_e6)) amount_e6 FROM transactions t "
            "JOIN ledger_entries l ON l.transaction_id=t.id JOIN accounts a ON a.id=l.account_id WHERE " + " AND ".join(where) + " GROUP BY t.id",
            tuple(params))
        return dict(row) | {"amount": from_e6(row["amount_e6"])} if row else None

    def history(self, date_from: str, date_to: str) -> list[dict]:
        """Owned money in and out with a counterparty, for spotting payments that repeat."""
        rows = self.db.all(
            "SELECT t.id,t.date,t.counterparty_id,c.name counterparty,l.account_id,l.category_id,l.effect,"
            "SUM(ABS(l.amount_base_e6)) amount_e6 FROM transactions t "
            "JOIN ledger_entries l ON l.transaction_id=t.id JOIN counterparties c ON c.id=t.counterparty_id "
            "WHERE t.status='POSTED' AND l.owner_id IS NULL AND l.effect IN ('INFLOW','OUTFLOW') "
            "AND t.type IN ('IN','OUT') AND t.date BETWEEN ? AND ? "
            "GROUP BY t.id,l.effect ORDER BY t.date", (date_from, date_to))
        return [dict(row) | {"amount": from_e6(row["amount_e6"])} for row in rows]

    @staticmethod
    def _row(values: dict) -> tuple:
        return (values["kind"], values["name"], to_e6(values["amount"]), values["frequency"],
                values["interval_count"], values["start_date"], values.get("end_date"), values.get("payment_count"),
                values.get("account_id"), values.get("category_id"), values.get("counterparty_id"),
                to_e6(values["principal"]) if values.get("principal") is not None else None,
                values.get("notes", ""), values.get("weekend_move", "none"), values.get("month_day"),
                values["match_window_days"], values["match_tolerance_pct"])
