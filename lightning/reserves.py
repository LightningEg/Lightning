"""Virtual cash reserves for upcoming needs and savings goals."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import now_iso, today
from lightning.core.errors import ConflictError, NotFoundError, ValidationError
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, from_e6, to_decimal, to_e6
from lightning.database.connection import Database


class CashReserveService:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _id(value, field: str) -> int:
        if (isinstance(value, bool) or
                not isinstance(value, int) and
                not (isinstance(value, str) and value.strip().isascii() and value.strip().isdigit())):
            raise ValidationError("Choose a valid saved item.", field)
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            raise ValidationError("Choose a valid saved item.", field) from None
        if parsed <= 0 or parsed > 9_223_372_036_854_775_807:
            raise ValidationError("Choose a valid saved item.", field)
        return parsed

    @request_cached(deep=True)
    def list_active(self):
        return [self._row(row) for row in self.db.all(
            "SELECT r.*,(SELECT COALESCE(SUM(l.amount_e6),0) FROM reserve_transaction_links l "
            "JOIN transactions t ON t.id=l.transaction_id WHERE l.reserve_id=r.id AND t.status='POSTED') AS spent_e6 "
            "FROM cash_reserves r WHERE r.status='ACTIVE' ORDER BY "
            "CASE r.kind WHEN 'EMERGENCY' THEN 0 ELSE 1 END,r.due_date IS NULL,r.due_date,r.name COLLATE NOCASE"
        )]

    def list_completed(self):
        return [self._row(row) for row in self.db.all(
            "SELECT r.*,(SELECT COALESCE(SUM(l.amount_e6),0) FROM reserve_transaction_links l "
            "JOIN transactions t ON t.id=l.transaction_id WHERE l.reserve_id=r.id AND t.status='POSTED') AS spent_e6 "
            "FROM cash_reserves r WHERE r.status='COMPLETE' AND r.kind!='EMERGENCY' "
            "ORDER BY r.due_date DESC,r.id DESC LIMIT 100"
        )]

    def cash_summary(self, owned_liquid_cash: Decimal, bills_due: Decimal = ZERO):
        """Free cash = owned liquid cash − assigned reserves − bills due (unpaid and already due)."""
        allocated = ZERO
        for row in self.list_active():
            allocated += row["effective_allocated"]
        return {"owned_liquid_cash": owned_liquid_cash, "allocated": allocated, "bills_due": bills_due,
                "free_cash": owned_liquid_cash - allocated - bills_due}

    def allocation_at(self, as_of: str):
        """Return active effective assignments at a date, or None if history is incomplete."""
        rows = self.breakdown_at(as_of)
        return None if rows is None else sum((row["effective_allocated"] for row in rows), ZERO)

    def breakdown_at(self, as_of: str):
        """Return the reconstructible active assignment for each reserve at a date."""
        rows = []
        for reserve in self.db.all("SELECT reserve_id AS id,created_date FROM reserve_allocation_history GROUP BY reserve_id,created_date"):
            created = reserve["created_date"]
            if created > as_of:
                continue
            first = self.db.one("SELECT effective_date FROM reserve_allocation_history WHERE reserve_id=? ORDER BY effective_date,id LIMIT 1",
                                (reserve["id"],))
            if not first or first["effective_date"] > as_of:
                return None
            row = self.db.one("SELECT allocated_e6,status FROM reserve_allocation_history WHERE reserve_id=? AND effective_date<=? ORDER BY effective_date DESC,id DESC LIMIT 1",
                              (reserve["id"], as_of))
            if row and row["status"] == "ACTIVE":
                spent = int(self.db.scalar(
                    "SELECT COALESCE(SUM(l.amount_e6),0) FROM reserve_transaction_links l "
                    "JOIN transactions t ON t.id=l.transaction_id WHERE l.reserve_id=? AND t.status='POSTED' AND t.date<=?",
                    (reserve["id"], as_of)) or 0)
                reserve_data = self.db.one("SELECT name,kind FROM cash_reserves WHERE id=?", (reserve["id"],))
                name = reserve_data["name"] if reserve_data else "Reserve"
                kind = reserve_data["kind"] if reserve_data else "PROJECT"
                rows.append({"id": reserve["id"], "name": name or "Reserve", "kind": kind,
                             "effective_allocated": max(from_e6(row["allocated_e6"]) - from_e6(spent), ZERO)})
        return rows

    def _record_allocation(self, reserve_id: int):
        row = self.db.one("SELECT allocated_e6,status,created_at FROM cash_reserves WHERE id=?", (reserve_id,))
        if row and self.db.has_table("reserve_allocation_history"):
            self.db.execute("INSERT INTO reserve_allocation_history(reserve_id,created_date,effective_date,allocated_e6,status) VALUES(?,?,?,?,?)",
                            (reserve_id, str(row["created_at"])[:10], today().isoformat(), row["allocated_e6"], row["status"]))

    def get(self, reserve_id: int):
        reserve_id = self._id(reserve_id, "reserve_id")
        row = self.db.one(
            "SELECT r.*,(SELECT COALESCE(SUM(l.amount_e6),0) FROM reserve_transaction_links l "
            "JOIN transactions t ON t.id=l.transaction_id WHERE l.reserve_id=r.id AND t.status='POSTED') AS spent_e6 "
            "FROM cash_reserves r WHERE r.id=?", (reserve_id,))
        if not row:
            raise NotFoundError("Reserve not found.")
        return self._row(row)

    def links_for_reserve(self, reserve_id: int):
        """Posted transactions reconciled to this reserve, newest first."""
        return self.db.all(
            "SELECT t.id,t.ref,t.date,t.counterparty,l.amount_e6 "
            "FROM reserve_transaction_links l JOIN transactions t ON t.id=l.transaction_id "
            "WHERE l.reserve_id=? AND t.status='POSTED' ORDER BY t.date DESC,t.id DESC",
            (reserve_id,),
        )

    def set_emergency_fund(self, amount, salary_target=ZERO):
        """Set what the Emergency Fund holds now. Payments already taken from the fund are added back,
        so typing the figure every screen shows (set aside less what was used) changes nothing."""
        value = to_decimal(amount, "allocated")
        if value < ZERO:
            raise ValidationError("Reserved cash cannot be negative.", "allocated")
        target = max(to_decimal(salary_target, "target"), value, Decimal("0.01"))
        active = self.db.one("SELECT id FROM cash_reserves WHERE kind='EMERGENCY' AND status='ACTIVE'")
        if not active and value == ZERO:
            raise ValidationError("Enter the amount you have reserved for emergencies.", "allocated")
        with self.db.transaction():
            if active:
                used = from_e6(int(self.db.scalar(
                    "SELECT COALESCE(SUM(l.amount_e6),0) FROM reserve_transaction_links l JOIN transactions t "
                    "ON t.id=l.transaction_id WHERE l.reserve_id=? AND t.status='POSTED'", (active["id"],)) or 0))
                self.db.execute("UPDATE cash_reserves SET target_e6=?,updated_at=? WHERE id=?",
                                (to_e6(max(target, value + used)), now_iso(), active["id"]))
                return self.allocate(int(active["id"]), value + used)
            reserve = self.create("Emergency Fund", target, "EMERGENCY")
            return self.allocate(reserve["id"], value)

    def create(self, name: str, target, kind: str = "PROJECT", due_date: str | None = None,
               recurrence: str = "NONE", counterparty_id: int | None = None,
               category_id: int | None = None, account_id: int | None = None):
        name = " ".join((name or "").split())
        if not name:
            raise ValidationError("Enter a name for this reserve.", "name")
        kind = str(kind or "PROJECT").upper()
        if kind not in {"PROJECT", "EMERGENCY"}:
            raise ValidationError("Choose an emergency fund or project.", "kind")
        if kind == "EMERGENCY":
            name = "Emergency Fund"
        recurrence = self._recurrence(recurrence, kind, due_date)
        target_value = to_decimal(target, "target")
        if target_value <= ZERO:
            raise ValidationError("Enter a target greater than zero.", "target")
        day = self._date(due_date) if due_date else None
        self._validate_counterparty(counterparty_id)
        self._validate_category(category_id)
        self._validate_account(account_id)
        now = now_iso()
        try:
            cur = self.db.execute(
                "INSERT INTO cash_reserves(name,kind,target_e6,due_date,created_at,updated_at,recurrence,recurrence_day,counterparty_id,category_id,account_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (name, kind, to_e6(target_value), day, now, now, recurrence,
                 date.fromisoformat(day).day if day and recurrence != "NONE" else None, counterparty_id, category_id, account_id),
            )
            self._record_allocation(int(cur.lastrowid))
        except self.db.IntegrityError:
            if kind == "EMERGENCY" and self.db.scalar(
                "SELECT 1 FROM cash_reserves WHERE kind='EMERGENCY' AND status='ACTIVE'"
            ):
                raise ConflictError("An active emergency fund already exists.", "kind") from None
            raise
        return self.get(int(cur.lastrowid))

    def update(self, reserve_id: int, name: str, target, due_date: str | None, recurrence: str | None = None,
               counterparty_id: int | None = None, category_id: int | None = None,
               account_id: int | None = None):
        reserve = self.get(reserve_id)
        if reserve["kind"] == "EMERGENCY":
            raise ValidationError("The Emergency Fund is managed in its dedicated section.")
        name = " ".join((name or "").split())
        if not name:
            raise ValidationError("Enter a name for this reserve.", "name")
        target_value = to_decimal(target, "target")
        if target_value <= ZERO:
            raise ValidationError("Enter a target greater than zero.", "target")
        day = self._date(due_date) if due_date else None
        recurrence = self._recurrence(recurrence if recurrence is not None else reserve["recurrence"],
                                      reserve["kind"], day)
        self._validate_counterparty(counterparty_id)
        self._validate_category(category_id)
        self._validate_account(account_id)
        recurrence_day = (date.fromisoformat(day).day if day != reserve["due_date"] else
                          (reserve.get("recurrence_day") or date.fromisoformat(day).day)) if day and recurrence != "NONE" else None
        self.db.execute(
            "UPDATE cash_reserves SET name=?,target_e6=?,due_date=?,recurrence=?,recurrence_day=?,counterparty_id=?,category_id=?,account_id=?,updated_at=? WHERE id=?",
            (name, to_e6(target_value), day, recurrence, recurrence_day, counterparty_id, category_id, account_id, now_iso(), reserve_id),
        )
        return self.get(reserve_id)

    def allocate(self, reserve_id: int, amount):
        reserve = self.get(reserve_id)
        if reserve["status"] != "ACTIVE":
            raise ValidationError("Reopen this reserve before changing its assigned cash.")
        value = to_decimal(amount, "allocated")
        if value < ZERO:
            raise ValidationError("Assigned cash cannot be negative.", "allocated")
        linked = int(self.db.scalar(
            "SELECT COALESCE(SUM(l.amount_e6),0) FROM reserve_transaction_links l "
            "JOIN transactions t ON t.id=l.transaction_id WHERE l.reserve_id=? AND t.status='POSTED'",
            (reserve_id,),
        ) or 0)
        if to_e6(value) < linked:
            raise ValidationError("This amount is below payments already assigned to the reserve.", "allocated")
        self.db.execute(
            "UPDATE cash_reserves SET allocated_e6=?,updated_at=? WHERE id=? AND status='ACTIVE'",
            (to_e6(value), now_iso(), reserve_id),
        )
        self._record_allocation(reserve_id)
        return next((item for item in self.list_active() if item["id"] == reserve_id), self.get(reserve_id))

    def set_expense_link(self, reserve_id: int, transaction_id: int, amount):
        reserve_id = self._id(reserve_id, "reserve_id")
        transaction_id = self._id(transaction_id, "transaction_id")
        with self.db.transaction():
            return self._set_expense_link(reserve_id, transaction_id, amount)

    def _set_expense_link(self, reserve_id: int, transaction_id: int, amount):
        reserve = self.get(reserve_id)
        if reserve["status"] != "ACTIVE":
            raise ValidationError("Choose an active reserve.")
        value = to_decimal(amount, "amount")
        if value <= ZERO:
            raise ValidationError("Enter an amount greater than zero.", "amount")
        txn = self.db.one("SELECT id,status,type,description FROM transactions WHERE id=?", (transaction_id,))
        external_expense = bool(txn and txn["type"] == "ADJ" and
                                (txn["description"] or "").startswith("Ownership: expense paid by "))
        if not txn or txn["status"] != "POSTED" or (txn["type"] != "OUT" and not external_expense):
            raise ValidationError("Choose a posted expense transaction.")
        has_non_user_lines = self.db.scalar(
            "SELECT 1 FROM ledger_entries WHERE transaction_id=? AND owner_id IS NOT NULL", (transaction_id,))
        if (self.db.scalar("SELECT 1 FROM money_from_others WHERE transaction_id=?", (transaction_id,)) or
                (has_non_user_lines and not external_expense)):
            raise ValidationError("Money held for others cannot be assigned to your reserve.")
        total_e6 = int(self.db.scalar(
            "SELECT COALESCE(SUM(ABS(le.amount_base_e6)),0) FROM ledger_entries le "
            "JOIN financial_assets a ON a.id=le.asset_id WHERE le.transaction_id=? AND a.is_cash=1 "
            "AND le.effect='OUTFLOW' AND le.owner_id IS NULL",
            (transaction_id,),
        ) or 0)
        if total_e6 <= 0:
            raise ValidationError("This transaction has no expense amount to assign.")
        old = self.db.one("SELECT id,amount_e6 FROM reserve_transaction_links WHERE reserve_id=? AND transaction_id=?",
                          (reserve_id, transaction_id))
        other_for_txn = int(self.db.scalar(
            "SELECT COALESCE(SUM(amount_e6),0) FROM reserve_transaction_links WHERE transaction_id=? "
            "AND NOT (reserve_id=? AND transaction_id=?)", (transaction_id, reserve_id, transaction_id),
        ) or 0)
        if to_e6(value) + other_for_txn > total_e6:
            raise ValidationError("The amount assigned across reserves cannot exceed this transaction.", "amount")
        other_spent = int(self.db.scalar(
            "SELECT COALESCE(SUM(amount_e6),0) FROM reserve_transaction_links WHERE reserve_id=? "
            "AND transaction_id<>? AND transaction_id IN (SELECT id FROM transactions WHERE status='POSTED')",
            (reserve_id, transaction_id),
        ) or 0)
        if other_spent + to_e6(value) > int(reserve["allocated_e6"]):
            raise ValidationError("Assign more cash to this reserve before linking that much of the payment.", "amount")
        now = now_iso()
        self.db.execute(
            "INSERT INTO reserve_transaction_links(reserve_id,transaction_id,amount_e6,created_at,updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(reserve_id,transaction_id) DO UPDATE SET "
            "amount_e6=excluded.amount_e6,updated_at=excluded.updated_at",
            (reserve_id, transaction_id, to_e6(value), now, now),
        )
        total_spent = int(self.db.scalar(
            "SELECT COALESCE(SUM(l.amount_e6),0) FROM reserve_transaction_links l "
            "JOIN transactions t ON t.id=l.transaction_id WHERE l.reserve_id=? AND t.status='POSTED'",
            (reserve_id,),
        ) or 0)
        if reserve["recurrence"] != "NONE" and total_spent >= int(reserve["target_e6"]):
            next_due = self._next_due(reserve)
            if next_due:
                self.db.execute("UPDATE cash_reserves SET status='COMPLETE',updated_at=? WHERE id=?",
                                (now_iso(), reserve_id))
                self._record_allocation(reserve_id)
                following = self.create(reserve["name"], reserve["target"], "PROJECT", next_due,
                                         reserve["recurrence"], reserve["counterparty_id"], reserve.get("category_id"),
                                         reserve.get("account_id"))
                carry_forward = max(int(reserve["allocated_e6"]) - total_spent, 0)
                if carry_forward:
                    self.allocate(following["id"], from_e6(carry_forward))

    def auto_link_transaction(self, transaction_id: int) -> int:
        """Report ambiguous suggestions; reserve links are always confirmed in the UI."""
        candidates = self.suggested_reserves(transaction_id)
        return -1 if len(candidates) > 1 else 0

    def suggested_reserves(self, transaction_id: int) -> list[dict]:
        # A register page asks this for every spending row. A suggestion can use only the cash still
        # assigned to the reserve, and only up to its unpaid target. Linking always needs confirmation.
        return self.suggested_reserves_for_transactions((transaction_id,)).get(transaction_id, [])

    def suggested_reserves_for_transactions(self, transaction_ids) -> dict[int, list[dict]]:
        """Return register suggestions for many transactions using a fixed number of reads."""
        ids = list(dict.fromkeys(int(value) for value in transaction_ids))
        if not ids:
            return {}
        result = {transaction_id: [] for transaction_id in ids}
        eligible = self._eligible_reserves()
        if not eligible:
            return result
        facts = self._suggestion_facts(ids)
        return {transaction_id: self._suggestions_from_facts(facts.get(transaction_id), eligible)
                for transaction_id in ids}

    def _eligible_reserves(self):
        eligible = []
        for reserve in self.list_active():
            unpaid = max(reserve["target"] - reserve["spent"], ZERO)
            available = min(reserve["effective_allocated"], unpaid)
            if available > ZERO:
                eligible.append((reserve, available))
        return eligible

    def _suggestion_facts(self, transaction_ids) -> dict[int, dict]:
        values = ",".join("(?)" for _ in transaction_ids)
        params = tuple(transaction_ids)
        rows = self.db.all(
            "WITH selected(id) AS (VALUES " + values + "), "
            "ledger_facts AS ("
            "SELECT le.transaction_id,"
            "SUM(CASE WHEN a.is_cash=1 AND le.effect='OUTFLOW' AND le.owner_id IS NULL "
            "THEN ABS(le.amount_base_e6) ELSE 0 END) AS total_e6,"
            "MAX(CASE WHEN le.owner_id IS NOT NULL THEN 1 ELSE 0 END) AS has_non_user_lines,"
            "GROUP_CONCAT(DISTINCT le.category_id) AS categories,"
            "GROUP_CONCAT(DISTINCT CASE WHEN a.is_cash=1 AND le.quantity_e6<0 THEN le.account_id END) "
            "AS cash_accounts FROM ledger_entries le JOIN selected s ON s.id=le.transaction_id "
            "LEFT JOIN financial_assets a ON a.id=le.asset_id GROUP BY le.transaction_id), "
            "link_facts AS ("
            "SELECT l.transaction_id,SUM(l.amount_e6) AS linked_e6,GROUP_CONCAT(DISTINCT l.reserve_id) "
            "AS linked_reserves FROM reserve_transaction_links l JOIN selected s ON s.id=l.transaction_id "
            "JOIN transactions linked_tx ON linked_tx.id=l.transaction_id AND linked_tx.status='POSTED' "
            "GROUP BY l.transaction_id) "
            "SELECT t.id,t.counterparty_id,t.type,t.status,t.description,"
            "COALESCE(l.total_e6,0) AS total_e6,COALESCE(l.has_non_user_lines,0) AS has_non_user_lines,"
            "l.categories,l.cash_accounts,COALESCE(f.linked_e6,0) AS linked_e6,f.linked_reserves,"
            "EXISTS(SELECT 1 FROM money_from_others m WHERE m.transaction_id=t.id) AS in_custody "
            "FROM selected s JOIN transactions t ON t.id=s.id "
            "LEFT JOIN ledger_facts l ON l.transaction_id=t.id "
            "LEFT JOIN link_facts f ON f.transaction_id=t.id", params)
        def parsed_ids(raw):
            return {int(value) for value in (raw or "").split(",") if value}
        return {int(row["id"]): dict(row) | {"categories_set": parsed_ids(row["categories"]),
                                             "cash_accounts_set": parsed_ids(row["cash_accounts"]),
                                             "linked_reserves_set": parsed_ids(row["linked_reserves"])}
                for row in rows}

    @staticmethod
    def _suggestions_from_facts(transaction, eligible) -> list[dict]:
        if not transaction:
            return []
        external_expense = (transaction["type"] == "ADJ" and
                            (transaction["description"] or "").startswith("Ownership: expense paid by "))
        if ((transaction["type"] != "OUT" and not external_expense) or transaction["status"] != "POSTED"):
            return []
        remaining = int(transaction["total_e6"]) - int(transaction["linked_e6"])
        if (remaining <= 0 or transaction["in_custody"] or
                (transaction["has_non_user_lines"] and not external_expense)):
            return []
        candidates = []
        for reserve, available in eligible:
            if reserve["id"] in transaction["linked_reserves_set"]:
                continue
            checks = []
            if reserve["counterparty_id"] is not None:
                checks.append(reserve["counterparty_id"] == transaction["counterparty_id"])
            if reserve["category_id"] is not None:
                checks.append(reserve["category_id"] in transaction["categories_set"])
            if reserve.get("account_id") is not None:
                checks.append(reserve["account_id"] in transaction["cash_accounts_set"])
            matched = checks and all(checks)
            amount_e6 = min(remaining, to_e6(available))
            if matched and amount_e6 > 0:
                amount = from_e6(amount_e6)
                candidates.append({"id": reserve["id"], "name": reserve["name"], "amount": amount,
                                   "remaining_after": max(reserve["effective_allocated"] - amount, ZERO)})
        return candidates

    def unlink_expense(self, reserve_id: int, transaction_id: int):
        self.db.execute("DELETE FROM reserve_transaction_links WHERE reserve_id=? AND transaction_id=?",
                        (reserve_id, transaction_id))

    def links_for_transaction(self, transaction_id: int):
        rows = [dict(row) for row in self.db.all(
            "SELECT l.reserve_id,r.name,r.kind,l.amount_e6 FROM reserve_transaction_links l "
            "JOIN cash_reserves r ON r.id=l.reserve_id JOIN transactions t ON t.id=l.transaction_id "
            "WHERE l.transaction_id=? AND t.status='POSTED' ORDER BY r.name COLLATE NOCASE", (transaction_id,)
        )]
        for row in rows:
            row["amount"] = from_e6(row["amount_e6"])
        return rows

    def complete(self, reserve_id: int):
        reserve = self.get(reserve_id)
        if reserve["kind"] == "EMERGENCY":
            raise ValidationError("The Emergency Fund cannot be completed or archived.")
        self.db.execute("UPDATE cash_reserves SET status='COMPLETE',updated_at=? WHERE id=?",
                        (now_iso(), reserve_id))
        self._record_allocation(reserve_id)
        return self.get(reserve_id)

    def delete(self, reserve_id: int):
        reserve = self.get(reserve_id)
        if reserve["kind"] == "EMERGENCY":
            raise ValidationError("The Emergency Fund cannot be deleted.")
        self.db.execute("INSERT INTO reserve_allocation_history(reserve_id,created_date,effective_date,allocated_e6,status) VALUES(?,?,?,?,?)",
                        (reserve_id, str(reserve["created_at"])[:10], today().isoformat(), reserve["allocated_e6"], "DELETED"))
        self.db.execute("DELETE FROM cash_reserves WHERE id=?", (reserve_id,))

    @staticmethod
    def _row(row):
        item = dict(row)
        item["target"] = from_e6(item["target_e6"])
        item["allocated"] = from_e6(item["allocated_e6"])
        item["spent"] = from_e6(item.get("spent_e6", 0))
        item["effective_allocated"] = max(item["allocated"] - item["spent"], ZERO)
        credited = item["allocated"] if item["kind"] == "PROJECT" else item["effective_allocated"]
        item["remaining"] = max(item["target"] - credited, ZERO)
        item["progress"] = min(credited / item["target"] * 100, Decimal(100))
        return item

    @staticmethod
    def _date(value: str) -> str:
        try:
            return date.fromisoformat(str(value)).isoformat()
        except (TypeError, ValueError):
            raise ValidationError("Enter a valid due date.", "due_date") from None

    @staticmethod
    def _recurrence(value: str, kind: str, due_date: str | None) -> str:
        recurrence = str(value or "NONE").upper()
        if recurrence not in {"NONE", "WEEKLY", "MONTHLY", "YEARLY"}:
            raise ValidationError("Choose a supported repeat interval.", "recurrence")
        if kind == "EMERGENCY" and recurrence != "NONE":
            raise ValidationError("Emergency funds do not repeat on a schedule.", "recurrence")
        if recurrence != "NONE" and not due_date:
            raise ValidationError("Choose a due date for a repeating project.", "due_date")
        return recurrence

    def _validate_counterparty(self, counterparty_id: int | None) -> None:
        if counterparty_id is not None and not self.db.scalar(
            "SELECT 1 FROM counterparties WHERE id=? AND active=1", (counterparty_id,)
        ):
            raise ValidationError("Choose an active saved Counterparty.", "counterparty_id")

    def _validate_category(self, category_id: int | None) -> None:
        if category_id is not None and not self.db.scalar(
                "SELECT 1 FROM categories WHERE id=? AND movement='OUTFLOW' AND active=1 AND is_system=0",
                (category_id,)):
            raise ValidationError("Choose an active spending category.", "category_id")

    def _validate_account(self, account_id: int | None) -> None:
        if account_id is not None and not self.db.scalar(
                "SELECT 1 FROM accounts WHERE id=? AND active=1", (account_id,)):
            raise ValidationError("Choose an active account.", "account_id")

    @staticmethod
    def _next_due(reserve) -> str | None:
        recurrence = reserve["recurrence"]
        if not recurrence or recurrence == "NONE" or not reserve["due_date"]:
            return None
        current = date.fromisoformat(reserve["due_date"])
        if recurrence == "WEEKLY":
            return (current + timedelta(days=7)).isoformat()
        if recurrence == "YEARLY":
            year, month, day = current.year + 1, current.month, int(reserve.get("recurrence_day") or current.day)
            day = min(day, calendar.monthrange(year, month)[1])
            return date(year, month, day).isoformat()
        month_index = current.year * 12 + current.month
        year, month = divmod(month_index, 12)
        day = min(int(reserve.get("recurrence_day") or current.day), calendar.monthrange(year, month + 1)[1])
        return date(year, month + 1, day).isoformat()
