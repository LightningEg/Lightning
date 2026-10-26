"""Explicit reimbursement claims and their cash receipts.

Claims annotate existing transactions. They never post ledger entries or create cash.
All amounts are stored in the profile's base currency using each ledger line's recorded FX value.
"""

from __future__ import annotations

from datetime import date

from lightning.core.dates import now_iso
from lightning.core.errors import ConflictError, NotFoundError, ValidationError
from lightning.core.money import check_places, from_e6, to_decimal, to_e6
from lightning.core.refs import parse_row_id
from lightning.database.connection import Database
from lightning.database.currencies import minor_units
from lightning.database.settings import SettingsStore


class ReimbursementService:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _id(value, field: str) -> int:
        return parse_row_id(value, field)

    def _require_writable(self) -> None:
        if self.db.read_only:
            raise ValidationError("This copy is read-only.")

    def _expense_capacity(self, transaction_id: int) -> dict:
        transaction_id = self._id(transaction_id, "transaction_id")
        return self._expense_capacities([transaction_id])[transaction_id]

    def _expense_capacities(self, transaction_ids: list[int] | None = None) -> dict[int, dict]:
        """Each expense's reimbursable amount, in six reads whatever the count (9I).

        ``None`` reads every posted expense, newest first; a list reads those transactions, whatever they are.
        """
        if transaction_ids is None:
            scope, params, order = "t.type='OUT' AND t.status='POSTED'", (), " ORDER BY t.date DESC,t.id DESC"
        else:
            scope, params, order = f"t.id IN ({','.join('?' for _ in transaction_ids)})", tuple(transaction_ids), ""
        transactions = {int(row["id"]): row for row in self.db.all(
            "SELECT t.id,t.ref,t.type,t.date,t.status,t.description,t.counterparty,t.counterparty_id "
            f"FROM transactions t WHERE {scope}{order}", params)}
        # Money from others and another owner's lines are not the user's expense.
        shared = {int(row["id"]) for row in self.db.all(
            f"SELECT t.id FROM transactions t WHERE {scope} AND ("
            "EXISTS (SELECT 1 FROM money_from_others m WHERE m.transaction_id=t.id) OR "
            "EXISTS (SELECT 1 FROM ledger_entries le WHERE le.transaction_id=t.id AND le.owner_id IS NOT NULL))",
            params)}
        # Owned expense is the user's posted cash outflow, grouped by account/category.
        expense_e6: dict[int, int] = {}
        for row in self.db.all(
                "SELECT le.transaction_id tid,le.account_id,le.category_id,SUM(ABS(le.amount_base_e6)) AS amount_e6 "
                "FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
                f"JOIN financial_assets a ON a.id=le.asset_id WHERE {scope} "
                "AND a.is_cash=1 AND le.effect='OUTFLOW' AND le.owner_id IS NULL "
                "GROUP BY le.transaction_id,le.account_id,le.category_id", params):
            tid = int(row["tid"])
            expense_e6[tid] = expense_e6.get(tid, 0) + int(row["amount_e6"] or 0)
        suggested: dict[int, bool] = {}
        for row in self.db.all(
                "SELECT DISTINCT le.transaction_id tid,c.default_reimbursable FROM transactions t "
                "JOIN ledger_entries le ON le.transaction_id=t.id JOIN categories c ON c.id=le.category_id "
                f"WHERE {scope} AND le.effect='OUTFLOW' AND le.owner_id IS NULL", params):
            tid = int(row["tid"])
            suggested[tid] = suggested.get(tid, False) or bool(row["default_reimbursable"])
        categories: dict[int, list[str]] = {}
        for row in self.db.all(
                "SELECT DISTINCT le.transaction_id tid,c.name FROM transactions t "
                "JOIN ledger_entries le ON le.transaction_id=t.id JOIN categories c ON c.id=le.category_id "
                f"WHERE {scope} AND le.effect='OUTFLOW' AND le.owner_id IS NULL "
                "ORDER BY le.transaction_id,c.name COLLATE NOCASE", params):
            categories.setdefault(int(row["tid"]), []).append(row["name"])
        accounts: dict[int, list[str]] = {}
        for row in self.db.all(
                "SELECT DISTINCT le.transaction_id tid,ac.id,ac.name FROM transactions t "
                "JOIN ledger_entries le ON le.transaction_id=t.id JOIN financial_assets a ON a.id=le.asset_id "
                f"JOIN accounts ac ON ac.id=le.account_id WHERE {scope} "
                "AND a.is_cash=1 AND le.effect='OUTFLOW' AND le.owner_id IS NULL "
                "ORDER BY le.transaction_id,ac.name COLLATE NOCASE", params):
            accounts.setdefault(int(row["tid"]), []).append(row["name"])

        result: dict[int, dict] = {}
        for transaction_id in (list(transactions) if transaction_ids is None else transaction_ids):
            transaction = transactions.get(transaction_id)
            nothing = {"transaction_id": transaction_id, "expense_e6": 0, "refund_e6": 0, "net_e6": 0,
                       "eligible": False}
            if not transaction:
                result[transaction_id] = nothing
                continue
            amount_e6 = expense_e6.get(transaction_id, 0)
            if (transaction["type"] != "OUT" or transaction["status"] != "POSTED" or transaction_id in shared or
                    amount_e6 <= 0):
                result[transaction_id] = {**nothing, "transaction": transaction}
                continue
            # A refund is not identified by category/date alone: another purchase can
            # share both. Explicitly linked refunds and repayments reduce outstanding
            # once, through receipt links.
            result[transaction_id] = {
                "transaction_id": transaction_id, "transaction": transaction, "expense_e6": amount_e6,
                "refund_e6": 0, "net_e6": amount_e6, "eligible": amount_e6 > 0,
                "suggested": suggested.get(transaction_id, False),
                "categories": categories.get(transaction_id, []),
                "accounts": accounts.get(transaction_id, [])}
        return result

    def _receipt_capacity(self, transaction_id: int) -> dict:
        return self._receipt_capacities([transaction_id])[transaction_id]

    def _receipt_capacities(self, transaction_ids: list[int] | None = None) -> dict[int, dict]:
        """Each receipt's owned cash inflow, in two reads whatever the count (9I).

        ``None`` reads every posted money in, newest first; a list reads those transactions, whatever they are.
        """
        if transaction_ids is None:
            scope, params, order = "t.type='IN' AND t.status='POSTED'", (), " ORDER BY t.date DESC,t.id DESC"
        else:
            scope, params, order = f"t.id IN ({','.join('?' for _ in transaction_ids)})", tuple(transaction_ids), ""
        transactions = {int(row["id"]): row for row in self.db.all(
            "SELECT t.id,t.ref,t.type,t.date,t.status,t.description,t.counterparty "
            f"FROM transactions t WHERE {scope}{order}", params)}
        amounts = {int(row["tid"]): int(row["amount_e6"] or 0) for row in self.db.all(
            "SELECT le.transaction_id tid,SUM(ABS(le.amount_base_e6)) amount_e6 FROM transactions t "
            "JOIN ledger_entries le ON le.transaction_id=t.id JOIN financial_assets a ON a.id=le.asset_id "
            f"WHERE {scope} AND a.is_cash=1 AND le.quantity_e6>0 AND le.effect IN ('INFLOW','OUTFLOW') "
            "AND le.owner_id IS NULL AND COALESCE(le.category_id,0) NOT IN "
            "(SELECT id FROM categories WHERE code='EXP.SYSTEM.CUSTODY') GROUP BY le.transaction_id", params)}
        result: dict[int, dict] = {}
        for transaction_id in (list(transactions) if transaction_ids is None else transaction_ids):
            transaction = transactions.get(transaction_id)
            if not transaction or transaction["type"] != "IN" or transaction["status"] != "POSTED":
                result[transaction_id] = {"transaction_id": transaction_id, "amount_e6": 0, "eligible": False,
                                          "transaction": transaction}
                continue
            amount_e6 = amounts.get(transaction_id, 0)
            result[transaction_id] = {"transaction_id": transaction_id, "transaction": transaction,
                                      "amount_e6": amount_e6, "eligible": amount_e6 > 0}
        return result

    def eligible_expenses(self) -> list[dict]:
        claimed = {int(row["expense_id"]) for row in self.db.all(
            "SELECT expense_id FROM reimbursement_claims WHERE expense_id IS NOT NULL")}
        expenses = []
        for transaction_id, info in self._expense_capacities().items():
            if transaction_id in claimed:
                continue
            if info["eligible"]:
                info["max_amount"] = from_e6(info["net_e6"])
                expenses.append(info)
        # Query order is newest first; stable sorting moves suggested categories to the top.
        expenses.sort(key=lambda row: not row.get("suggested", False))
        return expenses

    def _claim_summary(self, row) -> dict:
        claim = dict(row)
        claim["expected"] = from_e6(claim["expected_e6"])
        expense = self._expense_capacity(claim["expense_id"]) if claim["expense_id"] is not None else {
            "eligible": False, "net_e6": 0, "transaction": None, "categories": [], "accounts": []}
        current_limit = min(claim["expected_e6"], int(expense.get("net_e6", 0)))
        links = self.db.all(
            "SELECT rr.*,t.ref,t.date,t.description,t.counterparty,t.type,t.status "
            "FROM reimbursement_receipts rr LEFT JOIN transactions t ON t.id=rr.receipt_id "
            "WHERE rr.claim_id=? ORDER BY rr.id", (claim["id"],),
        )
        receipt_rows = []
        received_e6 = 0
        issues = []
        for link in links:
            link = dict(link)
            link["amount"] = from_e6(link["amount_e6"])
            capacity = self._receipt_capacity(link["receipt_id"]) if link["receipt_id"] is not None else {
                "eligible": False, "amount_e6": 0, "transaction": None}
            valid_e6 = min(link["amount_e6"], int(capacity["amount_e6"])) if capacity["eligible"] else 0
            link["counted"] = from_e6(valid_e6)
            link["issue"] = None
            if not capacity["eligible"]:
                link["issue"] = "Receipt is no longer a posted owned cash inflow."
                issues.append(link["issue"])
            elif valid_e6 < link["amount_e6"]:
                link["issue"] = "Receipt amount changed below the amount linked here."
                issues.append(link["issue"])
            received_e6 += valid_e6
            receipt_rows.append(link)
        txn = expense.get("transaction")
        if claim["expense_id"] is None or not txn or txn["type"] != "OUT" or txn["status"] != "POSTED":
            issues.append("The linked expense is no longer a posted owned expense.")
        elif not expense.get("eligible"):
            issues.append("The expense no longer has an eligible owned amount.")
        elif claim["expected_e6"] > int(expense["net_e6"]):
            issues.append("The expense changed; the claim exceeds its current owned amount.")
        if received_e6 > current_limit:
            issues.append("Linked receipts now exceed the current claim amount.")
        claim.update({"expense": expense.get("transaction"), "current_expense": from_e6(int(expense.get("net_e6", 0))),
                      "categories": expense.get("categories", []), "accounts": expense.get("accounts", []),
                      "receipts": receipt_rows, "received": from_e6(received_e6),
                      "outstanding": from_e6(max(current_limit - received_e6, 0)),
                      "over_received": from_e6(max(received_e6 - current_limit, 0)),
                      "issues": issues})
        return claim

    def list_claims(self) -> list[dict]:
        rows = self.db.all(
            "SELECT rc.*,cp.name AS payer_name FROM reimbursement_claims rc "
            "LEFT JOIN counterparties cp ON cp.id=rc.payer_id "
            "ORDER BY CASE WHEN rc.due_date IS NULL THEN 1 ELSE 0 END,rc.due_date,rc.id DESC"
        )
        return [self._claim_summary(row) for row in rows]

    def available_receipts(self) -> list[dict]:
        used = {int(row["receipt_id"]) for row in self.db.all(
            "SELECT receipt_id FROM reimbursement_receipts WHERE receipt_id IS NOT NULL")}
        interest = {int(row["transaction_id"]) for row in self.db.all(
            "SELECT transaction_id FROM cd_interest_receipt_links WHERE transaction_id IS NOT NULL")}
        receipts = []
        for transaction_id, info in self._receipt_capacities().items():
            if transaction_id in used or transaction_id in interest:
                continue
            if info["eligible"]:
                info["amount"] = from_e6(info["amount_e6"])
                receipts.append(info)
        return receipts

    def _money(self, value, field):
        """Whole minor units of the profile currency, as every other money field (audit 2026-10-26)."""
        return check_places(to_decimal(value, field), minor_units(SettingsStore(self.db).base_currency), field)

    def create_claim(self, transaction_id: int, expected, payer_id: int | None = None,
                     due_date: str | None = None) -> dict:
        self._require_writable()
        transaction_id = self._id(transaction_id, "transaction_id")
        if payer_id is not None:
            payer_id = self._id(payer_id, "payer_id")
        value = self._money(expected, "expected")
        value_e6 = to_e6(value)
        if value_e6 <= 0:
            raise ValidationError("Enter an expected amount greater than zero.", "expected")
        if due_date:
            try:
                parsed_date = date.fromisoformat(str(due_date))
            except (TypeError, ValueError):
                raise ValidationError("Enter a valid due date.", "due_date") from None
            if str(due_date) != parsed_date.isoformat():
                raise ValidationError("Enter a valid due date.", "due_date")
            due_date = parsed_date.isoformat()
        try:
            with self.db.transaction(undo_label="Create reimbursement claim"):
                expense = self._expense_capacity(int(transaction_id))
                if not expense["eligible"]:
                    raise ValidationError("Choose a posted owned cash expense with an amount still eligible for reimbursement.",
                                          "transaction_id")
                if value_e6 > int(expense["net_e6"]):
                    raise ValidationError("Expected reimbursement cannot exceed the owned expense amount.", "expected")
                if payer_id is not None and not self.db.scalar(
                        "SELECT 1 FROM counterparties WHERE id=? AND active=1", (payer_id,)):
                    raise ValidationError("Choose an active saved counterparty.", "payer_id")
                now = now_iso()
                cur = self.db.execute(
                    "INSERT INTO reimbursement_claims(expense_id,expected_e6,payer_id,due_date,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?)", (transaction_id, value_e6, payer_id, due_date, now, now),
                )
        except self.db.IntegrityError:
            raise ConflictError("This expense already has a reimbursement claim.", "transaction_id") from None
        row = self.db.one(
            "SELECT rc.*,cp.name AS payer_name FROM reimbursement_claims rc "
            "LEFT JOIN counterparties cp ON cp.id=rc.payer_id WHERE rc.id=?", (cur.lastrowid,),
        )
        return self._claim_summary(row)

    def link_receipt(self, claim_id: int, transaction_id: int, amount) -> dict:
        self._require_writable()
        claim_id = self._id(claim_id, "claim_id")
        transaction_id = self._id(transaction_id, "receipt_id")
        value = self._money(amount, "amount")
        value_e6 = to_e6(value)
        if value_e6 <= 0:
            raise ValidationError("Enter a receipt amount greater than zero.", "amount")
        try:
            with self.db.transaction(undo_label="Link reimbursement receipt"):
                claim = self.db.one("SELECT * FROM reimbursement_claims WHERE id=?", (claim_id,))
                if not claim:
                    raise NotFoundError("Reimbursement claim not found.")
                expense = self._expense_capacity(claim["expense_id"]) if claim["expense_id"] is not None else {"eligible": False}
                if not expense["eligible"]:
                    raise ValidationError("The linked expense needs review before a receipt can be added.")
                if self.db.scalar("SELECT 1 FROM cd_interest_receipt_links WHERE transaction_id=?", (transaction_id,)):
                    raise ValidationError("This receipt is already matched to certificate interest.")
                receipt = self._receipt_capacity(int(transaction_id))
                if not receipt["eligible"]:
                    raise ValidationError("Choose a posted owned cash inflow receipt.", "receipt_id")
                if self.db.scalar("SELECT 1 FROM reimbursement_receipts WHERE receipt_id=?", (transaction_id,)):
                    raise ConflictError("This receipt is already linked to a reimbursement claim.", "receipt_id")
                summary = self._claim_summary(claim)
                if value_e6 > to_e6(summary["outstanding"]):
                    raise ValidationError("Receipt amount cannot exceed the claim's current outstanding amount.", "amount")
                if value_e6 > int(receipt["amount_e6"]):
                    raise ValidationError("Receipt amount cannot exceed the posted owned inflow.", "amount")
                now = now_iso()
                cur = self.db.execute(
                    "INSERT INTO reimbursement_receipts(claim_id,receipt_id,amount_e6,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)", (claim_id, transaction_id, value_e6, now, now),
                )
        except self.db.IntegrityError:
            raise ConflictError("This receipt is already linked to a reimbursement claim.", "receipt_id") from None
        return {"id": int(cur.lastrowid), "claim_id": claim_id, "receipt_id": transaction_id,
                "amount": from_e6(value_e6)}

    def unlink_receipt(self, claim_id: int, link_id: int) -> None:
        self._require_writable()
        claim_id = self._id(claim_id, "claim_id")
        link_id = self._id(link_id, "link_id")
        with self.db.transaction(undo_label="Unlink reimbursement receipt"):
            cur = self.db.execute("DELETE FROM reimbursement_receipts WHERE id=? AND claim_id=?", (link_id, claim_id))
            if cur.rowcount == 0:
                raise NotFoundError("Linked receipt not found.")

    def delete_claim(self, claim_id: int) -> None:
        self._require_writable()
        claim_id = self._id(claim_id, "claim_id")
        with self.db.transaction(undo_label="Delete reimbursement claim"):
            cur = self.db.execute("DELETE FROM reimbursement_claims WHERE id=?", (claim_id,))
            if cur.rowcount == 0:
                raise NotFoundError("Reimbursement claim not found.")
