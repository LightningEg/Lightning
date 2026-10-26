"""SQL for the accounts table. Only this module touches it."""

from __future__ import annotations

import sqlite3

from lightning.core.dates import now_iso
from lightning.database.connection import Database

from .domain import Account, AccountType


def _row(row: sqlite3.Row) -> Account:
    return Account(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        institution=row["institution"],
        account_type=AccountType(row["account_type"]),
        currency=row["currency"],
        cash_class_id=row["cash_class_id"],
        opening_date=row["opening_date"],
        is_system=bool(row["is_system"]),
        last4=row["last4"],
        active=bool(row["active"]),
        sort_order=row["sort_order"],
        notes=row["notes"],
        cash_at_hand=bool(row["cash_at_hand"]),
        spendable=None if row["spendable"] is None else bool(row["spendable"]),
        parent_id=row["parent_id"],
    )


class AccountRepository:
    def __init__(self, db: Database):
        self.db = db

    def list(self, active_only: bool = False) -> list[Account]:
        sql = "SELECT * FROM accounts"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name COLLATE NOCASE, code COLLATE NOCASE"
        return [_row(r) for r in self.db.all(sql)]

    def get(self, account_id: int) -> Account | None:
        row = self.db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
        return _row(row) if row else None

    def code_exists(self, code: str, exclude_id: int | None = None) -> bool:
        return (
            self.db.scalar("SELECT 1 FROM accounts WHERE code = ? AND id IS NOT ?", (code, exclude_id))
            is not None
        )

    def next_sort_order(self) -> int:
        return (self.db.scalar("SELECT MAX(sort_order) FROM accounts") or 0) + 1

    def insert(self, a: Account) -> int:
        now = now_iso()
        cur = self.db.execute(
            "INSERT INTO accounts(code, name, institution, account_type, currency, cash_class_id,"
            " opening_date, is_system, last4, active, sort_order, notes, cash_at_hand, spendable, parent_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                a.code,
                a.name,
                a.institution,
                a.account_type.value,
                a.currency,
                a.cash_class_id,
                a.opening_date,
                int(a.is_system),
                a.last4,
                int(a.active),
                a.sort_order,
                a.notes,
                int(a.cash_at_hand),
                None if a.spendable is None else int(a.spendable),
                a.parent_id,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)

    def update(self, a: Account) -> None:
        self.db.execute(
            "UPDATE accounts SET code=?, name=?, institution=?, account_type=?, cash_class_id=?,"
            " opening_date=?, last4=?, active=?, sort_order=?, notes=?, cash_at_hand=?, spendable=?, updated_at=? WHERE id=?",
            (
                a.code,
                a.name,
                a.institution,
                a.account_type.value,
                a.cash_class_id,
                a.opening_date,
                a.last4,
                int(a.active),
                a.sort_order,
                a.notes,
                int(a.cash_at_hand),
                None if a.spendable is None else int(a.spendable),
                now_iso(),
                a.id,
            ),
        )
