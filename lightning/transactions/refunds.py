"""A refund names its purchase (NF-12AK3, owner 2026-11-13).

A link annotates two posted transactions: money back in an expense category (a refund) and the purchase it
returns. It never posts or changes ledger entries, so Cash, Spent and every report keep their real dates; only
the estimate basis (`BudgetService.estimate_spending`) reads it, counting the refund in the purchase's month.

Capacity follows reimbursement links: a link is never more than the refund, and a purchase's refunds and
reimbursement receipts together are never more than what it cost. This module is the only writer of
``refund_links``.
"""

from __future__ import annotations

from datetime import date, timedelta

from lightning.core.dates import now_iso
from lightning.core.errors import ConflictError, NotFoundError, ValidationError
from lightning.core.money import check_places, from_e6, to_decimal, to_e6
from lightning.core.refs import parse_row_id
from lightning.database.connection import Database
from lightning.database.currencies import minor_units
from lightning.database.settings import SettingsStore

# A purchase is offered for a refund up to six months back (owner, 2026-11-13).
PICK_DAYS = 183
# The user's own posted money in an ordinary expense category: what a refund or a purchase is made of.
_OWNED = ("le.category_id IS NOT NULL AND le.owner_id IS NULL AND c.movement='OUTFLOW' AND c.is_system=0 "
          "AND a.is_cash=1 AND le.effect='OUTFLOW'")


class RefundLinkService:
    def __init__(self, db: Database, transactions=None):
        self.db = db
        self.transactions = transactions  # TransactionService: records a refund from its purchase

    def _require_writable(self) -> None:
        if self.db.read_only:
            raise ValidationError("This copy is read-only.")

    def _money(self, value, field: str):
        return check_places(to_decimal(value, field), minor_units(SettingsStore(self.db).base_currency), field)

    # ------------------------------------------------------------------ facts
    def _lines(self, transaction_id: int, doc_type: str) -> dict[int, int]:
        """Per expense category, the owned amount of a posted transaction of ``doc_type`` (base currency, e6).
        A purchase's lines are money out, a refund's money back; both are read as positive amounts."""
        rows = self.db.all(
            "SELECT le.category_id,SUM(le.amount_base_e6) total_e6 FROM transactions t "
            "JOIN ledger_entries le ON le.transaction_id=t.id JOIN categories c ON c.id=le.category_id "
            "JOIN financial_assets a ON a.id=le.asset_id "
            f"WHERE t.id=? AND t.type=? AND t.status='POSTED' AND {_OWNED} "
            "AND NOT EXISTS (SELECT 1 FROM money_from_others m WHERE m.transaction_id=t.id) "
            "GROUP BY le.category_id", (transaction_id, doc_type))
        lines = {int(row["category_id"]): abs(int(row["total_e6"] or 0)) for row in rows}
        return {category: amount for category, amount in lines.items() if amount > 0}

    def _returned_e6(self, expense_id: int, *, besides_refund: int | None = None) -> int:
        """What has already come back for a purchase: its other refund links and its claim's receipts."""
        refunds = int(self.db.scalar(
            "SELECT COALESCE(SUM(amount_e6),0) FROM refund_links WHERE expense_id=? AND refund_id IS NOT ?",
            (expense_id, besides_refund)) or 0)
        receipts = int(self.db.scalar(
            "SELECT COALESCE(SUM(rr.amount_e6),0) FROM reimbursement_receipts rr "
            "JOIN reimbursement_claims rc ON rc.id=rr.claim_id WHERE rc.expense_id=?", (expense_id,)) or 0)
        return refunds + receipts

    def _transaction(self, transaction_id: int):
        return self.db.one("SELECT id,ref,type,date,status,description,counterparty FROM transactions WHERE id=?",
                           (transaction_id,))

    # ------------------------------------------------------------------ reads
    def refunded_purchase(self, refund_id) -> dict | None:
        """The purchase a refund names, with the amount linked, or None."""
        refund_id = parse_row_id(refund_id, "refund_id")
        row = self.db.one(
            "SELECT rl.id,rl.refund_id,rl.expense_id,rl.amount_e6,t.ref,t.date,t.description,t.counterparty,t.status "
            "FROM refund_links rl JOIN transactions t ON t.id=rl.expense_id WHERE rl.refund_id=?", (refund_id,))
        if not row:
            return None
        link = dict(row)
        link["amount"] = from_e6(link["amount_e6"])
        return link

    def refunds_of(self, expense_id) -> list[dict]:
        """The refunds that name a purchase, oldest first."""
        expense_id = parse_row_id(expense_id, "expense_id")
        rows = self.db.all(
            "SELECT rl.id,rl.refund_id,rl.amount_e6,t.ref,t.date,t.description,t.status FROM refund_links rl "
            "JOIN transactions t ON t.id=rl.refund_id WHERE rl.expense_id=? ORDER BY t.date,rl.id", (expense_id,))
        return [{**dict(row), "amount": from_e6(row["amount_e6"])} for row in rows]

    def room_for_refund(self, expense_id) -> dict | None:
        """What a purchase still has to return, and whether *Record a refund* can take it in one category; None
        when the transaction is not a posted purchase of the user's own."""
        expense_id = parse_row_id(expense_id, "expense_id")
        lines = self._lines(expense_id, "OUT")
        if not lines:
            return None
        left = max(sum(lines.values()) - self._returned_e6(expense_id), 0)
        return {"left": from_e6(left), "one_category": len(lines) == 1}

    def candidates(self, refund_id) -> list[dict]:
        """Purchases a refund can name: posted, in one of the refund's expense categories, from six months before
        it up to its date, with something still to return; newest first. Each carries the most it can take."""
        refund_id = parse_row_id(refund_id, "refund_id")
        refund = self._transaction(refund_id)
        lines = self._lines(refund_id, "IN") if refund else {}
        if not lines:
            return []
        last = date.fromisoformat(refund["date"][:10])
        first = (last - timedelta(days=PICK_DAYS)).isoformat()
        marks = ",".join("?" for _ in lines)
        rows = self.db.all(
            "SELECT DISTINCT t.id FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            f"WHERE t.type='OUT' AND t.status='POSTED' AND t.date BETWEEN ? AND ? AND le.category_id IN ({marks}) "
            "ORDER BY t.date DESC,t.id DESC", (first, last.isoformat(), *lines))
        offered = []
        for row in rows:
            expense_id = int(row["id"])
            room = self._room_e6(refund_id, expense_id, lines)
            if room > 0:
                expense = dict(self._transaction(expense_id))
                offered.append({**expense, "max_amount": from_e6(room)})
        return offered

    def _room_e6(self, refund_id: int, expense_id: int, refund_lines: dict[int, int] | None = None) -> int:
        """The most a link from this refund to this purchase can carry: the refund's amount in the categories
        they share, and what the purchase cost in them less what already came back for it."""
        refund_lines = self._lines(refund_id, "IN") if refund_lines is None else refund_lines
        expense_lines = self._lines(expense_id, "OUT")
        shared = set(refund_lines) & set(expense_lines)
        if not shared:
            return 0
        refund_e6 = sum(refund_lines[c] for c in shared)
        net_e6 = sum(expense_lines.values()) - self._returned_e6(expense_id, besides_refund=refund_id)
        return max(min(refund_e6, net_e6), 0)

    # ------------------------------------------------------------------ writes
    def link(self, refund_id, expense_id, amount=None) -> dict:
        """Name the purchase a refund returns (replacing any it named before). Without an amount the link takes
        the whole refund; more than the refund, or than the purchase has left to return, is refused."""
        self._require_writable()
        refund_id = parse_row_id(refund_id, "refund_id")
        expense_id = parse_row_id(expense_id, "expense_id")
        with self.db.transaction(undo_label="Link refund to its purchase"):
            refund_lines = self._lines(refund_id, "IN")
            if not refund_lines:
                raise ValidationError("Choose posted money back in an expense category.", "refund_id")
            if not self._lines(expense_id, "OUT"):
                raise ValidationError("Choose a posted purchase of your own.", "expense_id")
            refund, expense = self._transaction(refund_id), self._transaction(expense_id)
            if expense["date"][:10] > refund["date"][:10]:
                raise ValidationError("A refund can only return a purchase made on or before its date.", "expense_id")
            if self.db.scalar("SELECT 1 FROM reimbursement_receipts WHERE receipt_id=?", (refund_id,)):
                raise ConflictError("This money is already linked to a reimbursement claim.", "refund_id")
            room = self._room_e6(refund_id, expense_id, refund_lines)
            if room <= 0:
                raise ValidationError("Choose a purchase in the same category with something left to return.",
                                      "expense_id")
            value_e6 = room if amount in (None, "") else to_e6(self._money(amount, "amount"))
            if value_e6 <= 0:
                raise ValidationError("Enter an amount greater than zero.", "amount")
            if value_e6 > room:
                raise ValidationError("That is more than the refund, or more than the purchase has left to return.",
                                      "amount")
            now = now_iso()
            self.db.execute("DELETE FROM refund_links WHERE refund_id=?", (refund_id,))
            cur = self.db.execute(
                "INSERT INTO refund_links(refund_id,expense_id,amount_e6,created_at,updated_at) VALUES (?,?,?,?,?)",
                (refund_id, expense_id, value_e6, now, now))
        return {"id": int(cur.lastrowid), "refund_id": refund_id, "expense_id": expense_id,
                "amount": from_e6(value_e6)}

    def record_refund(self, expense_id, date: str, amount, notes: str = "") -> dict:
        """*Record a refund* on a purchase: money back to the purchase's account, in its category, already naming
        the purchase. One save: the refund and its link land together or not at all."""
        self._require_writable()
        expense_id = parse_row_id(expense_id, "expense_id")
        lines = self._lines(expense_id, "OUT")
        if not lines:
            raise ValidationError("Choose a posted purchase of your own.", "expense_id")
        if len(lines) > 1:
            raise ValidationError("This purchase is split across categories: record the refund from its account, "
                                  "then name the purchase on it.", "expense_id")
        account = self.db.one(
            "SELECT le.account_id FROM ledger_entries le JOIN financial_assets a ON a.id=le.asset_id "
            "WHERE le.transaction_id=? AND a.is_cash=1 AND le.owner_id IS NULL ORDER BY le.line_no LIMIT 1",
            (expense_id,))
        expense = self._transaction(expense_id)
        with self.db.transaction(undo_label="Record a refund"):
            refund = self.transactions.record_refund(
                date, int(account["account_id"]), amount, next(iter(lines)),
                description=f"Refund: {expense['description']}" if expense["description"] else "Refund",
                counterparty=expense["counterparty"] or "", notes=notes)
            link = self.link(refund.id, expense_id)
        return {**link, "ref": refund.ref}

    def unlink(self, refund_id) -> None:
        """The refund no longer names a purchase; estimates count it on its own date again."""
        self._require_writable()
        refund_id = parse_row_id(refund_id, "refund_id")
        with self.db.transaction(undo_label="Unlink refund from its purchase"):
            if self.db.execute("DELETE FROM refund_links WHERE refund_id=?", (refund_id,)).rowcount == 0:
                raise NotFoundError("This refund does not name a purchase.")
