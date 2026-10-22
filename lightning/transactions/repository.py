"""SQL for transactions and ledger_entries. Only this module writes them."""

from __future__ import annotations

import re
import sqlite3

from lightning.core.dates import now_iso
from lightning.core.ledger import Effect, PostingLine
from lightning.core.money import from_e6, to_e6
from lightning.core.refs import DocType, parse_ref
from lightning.database.connection import Database

from .domain import LedgerLine, Transaction, TxnFilter, TxnSource, TxnStatus  # noqa: F401


def _line(row: sqlite3.Row) -> LedgerLine:
    return LedgerLine(
        id=row["id"],
        transaction_id=row["transaction_id"],
        line_no=row["line_no"],
        date=row["date"],
        account_id=row["account_id"],
        asset_id=row["asset_id"],
        quantity=from_e6(row["quantity_e6"]),
        unit_price=from_e6(row["unit_price_e6"]),
        amount=from_e6(row["amount_e6"]),
        fx_rate=from_e6(row["fx_rate_e6"]),
        amount_base=from_e6(row["amount_base_e6"]),
        effect=Effect(row["effect"]),
        category_id=row["category_id"],
        memo=row["memo"],
        owner_id=row["owner_id"],
    )


def _header(row: sqlite3.Row) -> Transaction:
    return Transaction(
        id=row["id"],
        ref=row["ref"],
        type=DocType(row["type"]),
        date=row["date"],
        description=row["description"],
        counterparty=row["counterparty"],
        status=TxnStatus(row["status"]),
        source=TxnSource(row["source"]),
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _like(term: str) -> str:
    """A user word -> a safe LIKE pattern (so % and _ are matched literally)."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# One search word must appear somewhere in the transaction: its ref, date, counterparty, description, notes,
# or on one of its lines — account code/name, category code/name, or the amount (e.g. 450.00).
_TERM_SQL = (
    "(t.ref LIKE ? ESCAPE '\\' OR t.date LIKE ? ESCAPE '\\' OR t.counterparty LIKE ? ESCAPE '\\'"
    " OR t.description LIKE ? ESCAPE '\\' OR t.notes LIKE ? ESCAPE '\\'"
    " OR EXISTS (SELECT 1 FROM ledger_entries s JOIN accounts a ON a.id = s.account_id"
    " LEFT JOIN categories c ON c.id = s.category_id WHERE s.transaction_id = t.id AND ("
    " a.code LIKE ? ESCAPE '\\' OR a.name LIKE ? ESCAPE '\\' OR c.code LIKE ? ESCAPE '\\'"
    " OR c.name LIKE ? ESCAPE '\\' OR printf('%.2f', abs(s.amount_e6) / 1000000.0) LIKE ? ESCAPE '\\'"
    " OR CAST(abs(s.amount_e6) / 1000000.0 + 0.5 AS INTEGER) = ?)))"  # a whole number finds the figure the pages show
)


def search_terms(text: str) -> list[str]:
    """'Carrefour 10,000' -> ['Carrefour', '10000']: every word must match; thousands separators ignored."""
    terms = []
    for word in re.findall(r"\S+", text or ""):
        if re.fullmatch(r"[\d,.\-]+", word):
            word = word.replace(",", "").lstrip("-")
        if word:
            terms.append(word)
    return terms


class TransactionRepository:
    def __init__(self, db: Database):
        self.db = db

    # -- refs --------------------------------------------------------------
    def next_seq(self, prefix: str) -> int:
        # Refs starting with the prefix ("OUT-2026-09-25-") sort between it and the prefix with its
        # last character raised by one, so the ref index answers a range instead of a LIKE scan (9I).
        rows = self.db.all("SELECT ref FROM transactions WHERE ref>=? AND ref<?",
                           (prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)))
        return max((parse_ref(r["ref"])[2] for r in rows), default=0) + 1

    # -- writing -----------------------------------------------------------
    def insert(self, t: Transaction, lines: list[PostingLine], counterparty_id: int | None = None) -> int:
        now = now_iso()
        cur = self.db.execute(
            "INSERT INTO transactions(ref, type, date, description, counterparty, status, source,"
            " notes, created_at, updated_at, counterparty_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                t.ref,
                t.type.value,
                t.date,
                t.description,
                t.counterparty,
                t.status.value,
                t.source.value,
                t.notes,
                now,
                now,
                counterparty_id,
            ),
        )
        txn_id = int(cur.lastrowid)
        self._insert_lines(txn_id, t.date, lines)
        return txn_id

    def update_header(self, t: Transaction, counterparty_id: int | None = None) -> None:
        self.db.execute(
            "UPDATE transactions SET date=?, description=?, counterparty=?, status=?, notes=?,"
            " updated_at=?, counterparty_id=? WHERE id=?",
            (t.date, t.description, t.counterparty, t.status.value, t.notes, now_iso(), counterparty_id, t.id),
        )

    def replace_lines(self, txn_id: int, date: str, lines: list[PostingLine]) -> None:
        self.db.execute("DELETE FROM ledger_entries WHERE transaction_id = ?", (txn_id,))
        self._insert_lines(txn_id, date, lines)

    def set_status(self, txn_id: int, status: TxnStatus) -> None:
        self.db.execute(
            "UPDATE transactions SET status=?, updated_at=? WHERE id=?", (status.value, now_iso(), txn_id)
        )

    def _insert_lines(self, txn_id: int, date: str, lines: list[PostingLine]) -> None:
        for n, line in enumerate(lines, start=1):
            self.db.execute(
                "INSERT INTO ledger_entries(transaction_id, line_no, date, account_id, asset_id,"
                " quantity_e6, unit_price_e6, amount_e6, fx_rate_e6, amount_base_e6, effect,"
                " category_id, memo, owner_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    txn_id,
                    n,
                    date,
                    line.account_id,
                    line.asset_id,
                    to_e6(line.quantity),
                    to_e6(line.unit_price),
                    to_e6(line.amount),
                    to_e6(line.fx_rate),
                    to_e6(line.amount_base),
                    line.effect.value,
                    line.category_id,
                    line.memo,
                    line.owner_id,
                ),
            )

    # -- reading -----------------------------------------------------------
    def get(self, txn_id: int) -> Transaction | None:
        row = self.db.one("SELECT * FROM transactions WHERE id = ?", (txn_id,))
        if not row:
            return None
        t = _header(row)
        t.lines = self.lines_for([t.id])[t.id]
        return t

    def get_by_ref(self, ref: str) -> Transaction | None:
        txn_id = self.db.scalar("SELECT id FROM transactions WHERE ref = ?", (ref,))
        return self.get(txn_id) if txn_id else None

    def lines_for(self, txn_ids: list[int]) -> dict[int, list[LedgerLine]]:
        result: dict[int, list[LedgerLine]] = {i: [] for i in txn_ids}
        for start in range(0, len(txn_ids), 500):
            chunk = txn_ids[start : start + 500]
            marks = ",".join("?" * len(chunk))
            for row in self.db.all(
                f"SELECT * FROM ledger_entries WHERE transaction_id IN ({marks}) ORDER BY transaction_id, line_no",
                tuple(chunk),
            ):
                result[row["transaction_id"]].append(_line(row))
        return result

    def list(self, f: TxnFilter) -> tuple[list[Transaction], int]:
        clause, params = self._where(f)
        total = self.db.scalar(f"SELECT COUNT(*) FROM transactions t WHERE {clause}", tuple(params)) or 0
        rows = self.db.all(
            f"SELECT t.* FROM transactions t WHERE {clause} ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?",
            (*params, f.limit, f.offset),
        )
        txns = [_header(r) for r in rows]
        lines = self.lines_for([t.id for t in txns])
        for t in txns:
            t.lines = lines[t.id]
        return txns, int(total)

    def ids(self, f: TxnFilter) -> list[int]:
        """The ids `list` would return for the same filter, without building the transactions."""
        clause, params = self._where(f)
        rows = self.db.all(
            f"SELECT t.id FROM transactions t WHERE {clause} ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?",
            (*params, f.limit, f.offset),
        )
        return [int(row["id"]) for row in rows]

    @staticmethod
    def _where(f: TxnFilter) -> tuple[str, list]:
        where, params = ["1=1"], []
        if not f.include_void:
            where.append("t.status != 'VOID'")
        if f.account_id is not None:
            where.append("EXISTS (SELECT 1 FROM ledger_entries le WHERE le.transaction_id = t.id AND le.account_id = ?)")
            params.append(f.account_id)
        if f.category_ids:
            marks = ",".join("?" * len(f.category_ids))
            where.append(
                f"EXISTS (SELECT 1 FROM ledger_entries le WHERE le.transaction_id = t.id AND le.category_id IN ({marks}))"
            )
            params.extend(f.category_ids)
        if f.types:
            where.append(f"t.type IN ({','.join('?' * len(f.types))})")
            params.extend(t.value for t in f.types)
        if f.date_from:
            where.append("t.date >= ?")
            params.append(f.date_from)
        if f.date_to:
            where.append("t.date <= ?")
            params.append(f.date_to)
        for term in search_terms(f.search):
            where.append(_TERM_SQL)
            params.extend([_like(term)] * 10)
            params.append(int(term) if term.isdigit() else None)  # 3251 finds 3,250.75, shown as 3,251
        return " AND ".join(where), params

    def opening_txn_id(self, account_id: int, asset_id: int | None = None, exclude_id: int | None = None) -> int | None:
        """The live opening balance of an account's cash (asset_id None) or of one holding."""
        asset_rule = "le.asset_id = ?" if asset_id is not None else \
            "le.asset_id IN (SELECT id FROM financial_assets WHERE is_cash = 1)"
        params = [account_id] + ([asset_id] if asset_id is not None else []) + [exclude_id]
        return self.db.scalar(
            "SELECT t.id FROM transactions t JOIN ledger_entries le ON le.transaction_id = t.id"
            f" WHERE t.type = 'OPN' AND t.status != 'VOID' AND le.account_id = ? AND {asset_rule}"
            " AND t.id IS NOT ? ORDER BY t.id LIMIT 1",
            tuple(params),
        )

    def lowest_running_quantity(self, account_id: int, asset_id: int) -> tuple[int, str | None]:
        """Smallest quantity an (account, holding) ever reaches over time, and the date it happens."""
        row = self.db.one(
            "SELECT q, date FROM (SELECT le.date, SUM(le.quantity_e6) OVER (ORDER BY le.date, t.id, le.line_no)"
            " AS q FROM ledger_entries le JOIN transactions t ON t.id = le.transaction_id"
            " WHERE t.status = 'POSTED' AND le.account_id = ? AND le.asset_id = ?) ORDER BY q LIMIT 1",
            (account_id, asset_id),
        )
        return (int(row["q"]), row["date"]) if row else (0, None)

    def recent_categories(self, window: int) -> list:
        """Each counterparty's last ``window`` categorised transactions, newest first, under its saved
        name (so aliases count together); one row per transaction and category."""
        return self.db.all(
            "SELECT counterparty, category_id, date, id FROM ("
            " SELECT COALESCE(cp.name, t.counterparty) AS counterparty, le.category_id, t.date, t.id,"
            "  DENSE_RANK() OVER (PARTITION BY COALESCE(cp.name, t.counterparty) ORDER BY t.date DESC, t.id DESC) AS n"
            " FROM transactions t JOIN ledger_entries le ON le.transaction_id = t.id"
            " LEFT JOIN counterparties cp ON cp.id = t.counterparty_id"
            " WHERE t.status = 'POSTED' AND t.counterparty != '' AND le.category_id IS NOT NULL"
            " GROUP BY t.id, le.category_id"
            ") WHERE n <= ? ORDER BY counterparty, date DESC, id DESC",
            (window,),
        )

    def earliest_activity(self, account_id: int) -> str | None:
        return self.db.scalar(
            "SELECT MIN(le.date) FROM ledger_entries le JOIN transactions t ON t.id = le.transaction_id"
            " WHERE le.account_id = ? AND t.status = 'POSTED' AND t.type != 'OPN'",
            (account_id,),
        )

    def count_for_account(self, account_id: int) -> int:
        return int(
            self.db.scalar(
                "SELECT COUNT(DISTINCT le.transaction_id) FROM ledger_entries le"
                " JOIN transactions t ON t.id = le.transaction_id"
                " WHERE le.account_id = ? AND t.status != 'VOID'",
                (account_id,),
            )
            or 0
        )
