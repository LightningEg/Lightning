"""Explicit review actions for recent posted cash activity.

Review links existing ledger rows to plans and reserves. It never posts, edits, or
deletes cash. A submitted set of choices is checked again inside one undoable
database transaction before any of its annotations are saved.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from lightning.categories.domain import Movement
from lightning.core.dates import fmt_date, today
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.money import ZERO, to_decimal
from lightning.core.refs import parse_row_id


class ActivityReview:
    def __init__(self, container):
        self.c = container
        self.db = container.db

    @staticmethod
    def _id(value, field: str = "transaction_id") -> int:
        return parse_row_id(value, field, "Choose a valid activity or review option.", digits=False)

    def recent(self, limit: int = 100) -> list[dict]:
        """Recent posted, owned IN/OUT cash rows. Ambiguous ownership is left out."""
        limit = max(1, min(int(limit), 200))
        rows = self.db.all(
            "SELECT DISTINCT t.id FROM transactions t "
            "JOIN ledger_entries le ON le.transaction_id=t.id "
            "JOIN financial_assets a ON a.id=le.asset_id "
            "JOIN accounts ac ON ac.id=le.account_id "
            "WHERE t.status='POSTED' AND t.type IN ('IN','OUT') AND a.is_cash=1 "
            "AND ac.account_type IN ('CASH','BANK','BROKERAGE') AND le.owner_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM ledger_entries own WHERE own.transaction_id=t.id AND own.owner_id IS NOT NULL) "
            "AND NOT EXISTS (SELECT 1 FROM money_from_others mo WHERE mo.transaction_id=t.id) "
            "ORDER BY t.date DESC,t.id DESC LIMIT ?", (limit,))
        return [self.summary(int(row["id"]), include_choices=False) for row in rows]

    def summary(self, transaction_id: int, *, include_choices: bool = True) -> dict:
        transaction_id = self._id(transaction_id)
        txn = self.c.transactions.get(transaction_id)
        info = self._owned_cash(txn)
        categories = [self.c.categories.display_name(line.category_id)
                      for line in txn.lines if line.category_id]
        source_rows = self.db.all(
            "SELECT r.row_number,r.bank_reference,r.status,b.file_name,b.status AS batch_status,b.posted_at "
            "FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id "
            "WHERE r.transaction_id=? ORDER BY b.id,r.row_number", (transaction_id,))
        planned = self.db.all(
            "SELECT p.due_date,p.status,p.amount_e6,i.id AS item_id,i.name,i.kind "
            "FROM planned_payments p JOIN planned_items i ON i.id=p.planned_item_id "
            "WHERE p.transaction_id=? UNION ALL "
            "SELECT x.due_date,'PAID',x.principal_e6+x.fee_e6,i.id,i.name,i.kind "
            "FROM loan_extra_payments x JOIN planned_items i ON i.id=x.planned_item_id "
            "WHERE x.transaction_id=? ORDER BY due_date", (transaction_id, transaction_id))
        reserve_links = self.c.reserves.links_for_transaction(transaction_id)
        claim = None
        if include_choices and getattr(self.c, "reimbursements", None) and self.db.has_table("reimbursement_claims"):
            claim = next((row for row in self.c.reimbursements.list_claims()
                          if row.get("expense_id") == transaction_id), None)
        elif self.db.has_table("reimbursement_claims"):
            claim = self.db.one("SELECT id FROM reimbursement_claims WHERE expense_id=?", (transaction_id,))
        return {"txn": txn, "account_names": sorted({self.c.accounts.get(line.account_id).name
                                                       for line in info["cash_lines"]}),
                "currency": (self.c.accounts.get(info["cash_lines"][0].account_id).currency
                             if info["cash_lines"] else self.c.base_currency),
                "amount": info["amount"], "category_names": categories,
                "source_rows": [dict(row) for row in source_rows],
                "planned_links": [dict(row) for row in planned], "reserve_links": reserve_links,
                "claim": claim, "fingerprint": self.fingerprint(transaction_id),
                "can_recategorize": info["can_recategorize"],
                "categories": self._category_choices(txn.type) if info["can_recategorize"] else [],
                "planned_choices": self._planned_choices(txn) if include_choices else [],
                "reserve_choices": self.c.reserves.suggested_reserves(transaction_id)
                if include_choices and txn.type.value == "OUT" else []}

    def _owned_cash(self, txn) -> dict:
        if txn.is_void or txn.type.value not in {"IN", "OUT"}:
            raise ValidationError("This activity is no longer a posted cash income or expense.")
        cash_lines = [line for line in txn.lines if self.c.assets.get_asset(line.asset_id).is_cash]
        if (not cash_lines or any(line.owner_id is not None for line in txn.lines) or
                self.db.scalar("SELECT 1 FROM money_from_others WHERE transaction_id=?", (txn.id,))):
            raise ValidationError("This transaction is not fully owned cash activity.")
        effects = {"IN": "INFLOW", "OUT": "OUTFLOW"}
        owned = [line for line in cash_lines
                 if (line.quantity > ZERO if txn.type.value == "IN" else line.quantity < ZERO)]
        if not owned or len({line.account_id for line in owned}) != 1:
            raise ValidationError("This activity does not have one clear cash account.")
        amount = sum((abs(line.quantity) for line in owned), ZERO)
        category_lines = [line for line in txn.lines if line.category_id is not None]
        can_recat = (len(category_lines) == 1 and category_lines[0] in owned and
                     category_lines[0].effect.value == effects[txn.type.value])
        return {"cash_lines": owned, "amount": amount, "can_recategorize": can_recat}

    def _category_choices(self, txn_type) -> list:
        movement = Movement.INFLOW if txn_type.value == "IN" else Movement.OUTFLOW
        choices = []
        for cat in self.c.categories.tree(active_only=True):
            if not cat.active or cat.is_root or cat.is_system or cat.depth not in (2, 3) or cat.movement != movement:
                continue
            parent = self.c.categories.get(cat.parent_id) if cat.parent_id else None
            l2 = parent if cat.depth == 3 and parent else cat
            l1 = self.c.categories.get(l2.parent_id) if l2.parent_id else None
            choices.append({"id": cat.id, "name": cat.name, "parent": l1.name if l1 else "",
                            "level": cat.depth,
                            "order": f"{l2.name.casefold()}\u0000{cat.name.casefold() if cat.depth == 3 else ''}",
                            "label": self.c.categories.display_name(cat.id)})
        return choices

    def _planned_choices(self, txn) -> list[dict]:
        self._owned_cash(txn)
        choices = []
        linked = self.c.planning.linked_transaction_ids()
        if txn.id in linked:
            return choices
        as_of = today()
        for item in self.c.planning.items():
            if not (item.category_id or item.counterparty_id):
                continue
            end = date.fromisoformat(txn.date) + timedelta(days=item.match_window_days)
            for payment in self.c.planning.payments(item, fmt_date(end), as_of):
                if payment.status.value not in {"DUE", "UPCOMING"}:
                    continue
                if abs((date.fromisoformat(payment.due_date) - date.fromisoformat(txn.date)).days) > item.match_window_days:
                    continue
                if any(candidate["id"] == txn.id for candidate in
                       self.c.planning.candidates(payment, as_of, loose=True, any_account=True)):
                    choices.append({"item_id": item.id, "due_date": payment.due_date,
                                    "label": f"{item.name} · {payment.due_date}", "kind": item.kind.value})
        return sorted(choices, key=lambda row: (row["due_date"], row["label"].casefold()))

    def fingerprint(self, transaction_id: int) -> str:
        transaction_id = self._id(transaction_id)
        header = self.db.one("SELECT t.ref,t.type,t.date,t.description,t.counterparty,"
                             "COALESCE(cp.normalized_name,'' ) AS counterparty_identity,t.status,t.source,t.notes,t.updated_at "
                             "FROM transactions t LEFT JOIN counterparties cp ON cp.id=t.counterparty_id WHERE t.id=?",
                             (transaction_id,))
        if not header:
            raise NotFoundError("Transaction not found.")
        lines = self.db.all("SELECT le.line_no,le.date,a.code AS account,fa.code AS asset,le.quantity_e6,"
                            "le.unit_price_e6,le.amount_e6,le.fx_rate_e6,le.amount_base_e6,le.effect,"
                            "cat.code AS category,le.memo,COALESCE(owner.normalized_name,'') AS owner "
                            "FROM ledger_entries le JOIN accounts a ON a.id=le.account_id "
                            "JOIN financial_assets fa ON fa.id=le.asset_id "
                            "LEFT JOIN categories cat ON cat.id=le.category_id "
                            "LEFT JOIN counterparties owner ON owner.id=le.owner_id "
                            "WHERE le.transaction_id=? ORDER BY le.line_no", (transaction_id,))
        payload = {"header": list(header), "lines": [list(row) for row in lines]}
        return hashlib.sha256(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def apply(self, transaction_id: int, fingerprint: str, category_id: int | None = None,
              payment: str = "", reserve_id: int | None = None, reserve_amount: str = "") -> None:
        """Apply the explicitly selected annotations atomically; no choice is inferred."""
        if self.db.read_only:
            raise ValidationError("This copy is read-only.")
        transaction_id = self._id(transaction_id)
        if category_id is not None:
            category_id = self._id(category_id, "category_id")
        if reserve_id is not None:
            reserve_id = self._id(reserve_id, "reserve_id")
        if not any((category_id is not None, bool(payment), reserve_id is not None)):
            raise ValidationError("Choose a category, bill occurrence, or reserve suggestion first.")
        with self.db.transaction(undo_label="Review activity"):
            txn = self.c.transactions.get(transaction_id)
            before = self._owned_cash(txn)
            if self.fingerprint(transaction_id) != fingerprint:
                raise ValidationError("This transaction changed. Reload it and review the current details.")
            # Snapshot links because category editing replaces ledger rows and its trigger clears them.
            prior_links = self.db.all(
                "SELECT reserve_id,amount_e6,created_at,updated_at FROM reserve_transaction_links "
                "WHERE transaction_id=? ORDER BY reserve_id", (transaction_id,))
            if category_id is not None:
                if not before["can_recategorize"]:
                    raise ValidationError("This transaction does not have one category to change.")
                choices = {cat["id"] for cat in self._category_choices(txn.type)}
                if category_id not in choices:
                    raise ValidationError("Choose an active category for this transaction.")
            selected_reserve = None
            amount = None
            if reserve_id is not None:
                options = {int(row["id"]): row for row in self.c.reserves.suggested_reserves(transaction_id)}
                selected_reserve = options.get(reserve_id)
                if selected_reserve is None:
                    raise ValidationError("That reserve is no longer a current suggestion. Reload and review it.")
                amount = to_decimal(reserve_amount or selected_reserve["amount"], "reserve_amount")
                if amount <= ZERO or amount > selected_reserve["amount"]:
                    raise ValidationError("Enter a positive amount no greater than the suggested part.", "reserve_amount")
            selected_payment = None
            if payment:
                try:
                    item_text, due_date = payment.split("|", 1)
                    selected_payment = next((row for row in self._planned_choices(txn)
                                             if row["item_id"] == int(item_text) and row["due_date"] == due_date), None)
                except (ValueError, TypeError):
                    selected_payment = None
                if selected_payment is None:
                    raise ValidationError("That bill occurrence is no longer a current match. Reload and review it.")
            if category_id is not None:
                changed, skipped = self.c.transactions.set_category([transaction_id], category_id)
                if transaction_id not in changed or transaction_id in skipped:
                    raise ValidationError("This transaction could not be recategorized.")
                for link in prior_links:
                    self.db.execute(
                        "INSERT INTO reserve_transaction_links(reserve_id,transaction_id,amount_e6,created_at,updated_at) "
                        "VALUES (?,?,?,?,?)", (link["reserve_id"], transaction_id, link["amount_e6"],
                                                link["created_at"], link["updated_at"]))
            if selected_payment:
                self.c.planning.mark_paid(selected_payment["item_id"], selected_payment["due_date"], transaction_id)
            if selected_reserve:
                # A combined category change can change why this reserve matches. Recheck the
                # option against the updated ledger before attaching the annotation.
                refreshed = {int(row["id"]): row for row in self.c.reserves.suggested_reserves(transaction_id)}
                current_suggestion = refreshed.get(reserve_id)
                if current_suggestion is None or amount > current_suggestion["amount"]:
                    raise ValidationError("That reserve is no longer a current suggestion after the category change.")
                self.c.reserves.set_expense_link(reserve_id, transaction_id, amount)
