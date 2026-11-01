"""SQL for the categories table. Only this module touches it."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
import copy
import sqlite3

from lightning.core.dates import now_iso
from lightning.core.memo import in_request, request_cached
from lightning.database.connection import Database

from .domain import Category, CategoryFamily, Direction, IncomeClass, Movement, Scope


def _row(row: sqlite3.Row) -> Category:
    return Category(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        parent_id=row["parent_id"],
        movement=Movement(row["movement"]),
        scope=Scope(row["scope"]) if row["scope"] else None,
        income_class=IncomeClass(row["income_class"]) if row["income_class"] else None,
        family=CategoryFamily(row["family"]) if row["family"] else None,
        default_reimbursable=bool(row["default_reimbursable"]),
        is_system=bool(row["is_system"]),
        active=bool(row["active"]),
        sort_order=row["sort_order"],
        direction_set=Direction(row["direction"]) if "direction" in row.keys() and row["direction"] else None,
    )


class CategoryRepository:
    def __init__(self, db: Database):
        self.db = db

    @request_cached(deep=True)
    def list(self) -> list[Category]:
        return [_row(r) for r in self.db.all("SELECT * FROM categories ORDER BY sort_order, code")]

    def get(self, category_id: int) -> Category | None:
        row = self.db.one("SELECT * FROM categories WHERE id = ?", (category_id,))
        return _row(row) if row else None

    @request_cached
    def _by_code(self) -> Mapping[str, Category]:
        return MappingProxyType({row["code"]: _row(row) for row in self.db.all("SELECT * FROM categories")})

    def get_by_code(self, code: str) -> Category | None:
        # A report names many categories by code: during a request one read serves them all (IT-3AO4; Spending asked
        # 18 times). The caller gets its own copy.
        if in_request():
            found = self._by_code().get(code)
            return copy.copy(found) if found else None
        row = self.db.one("SELECT * FROM categories WHERE code = ?", (code,))
        return _row(row) if row else None

    def code_exists(self, code: str, exclude_id: int | None = None) -> bool:
        return (
            self.db.scalar(
                "SELECT 1 FROM categories WHERE code = ? AND id IS NOT ?", (code, exclude_id)
            )
            is not None
        )

    def next_sort_order(self) -> int:
        return (self.db.scalar("SELECT MAX(sort_order) FROM categories") or 0) + 1

    def insert(self, c: Category) -> int:
        now = now_iso()
        cur = self.db.execute(
            "INSERT INTO categories(code, name, parent_id, movement, scope, income_class, family,"
            " default_reimbursable, is_system, active, sort_order, direction, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                c.code,
                c.name,
                c.parent_id,
                c.movement.value,
                c.scope.value if c.scope else None,
                c.income_class.value if c.income_class else None,
                c.family.value if c.family else None,
                int(c.default_reimbursable),
                int(c.is_system),
                int(c.active),
                c.sort_order,
                c.direction_set.value if c.direction_set else None,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)

    def update(self, c: Category) -> None:
        self.db.execute(
            "UPDATE categories SET code=?, name=?, movement=?, scope=?, income_class=?, family=?, default_reimbursable=?,"
            " active=?, sort_order=?, direction=?, updated_at=? WHERE id=?",
            (
                c.code,
                c.name,
                c.movement.value,
                c.scope.value if c.scope else None,
                c.income_class.value if c.income_class else None,
                c.family.value if c.family else None,
                int(c.default_reimbursable),
                int(c.active),
                c.sort_order,
                c.direction_set.value if c.direction_set else None,
                now_iso(),
                c.id,
            ),
        )
