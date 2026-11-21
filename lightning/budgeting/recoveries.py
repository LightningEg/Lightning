"""Paid · returned · expected back · yours (NF-12AK5, owner 2026-11-13).

One purchase's money back, read from the claims service (receipts counted, what open claims still wait for) and the
refund links (posted refunds that name the purchase). A refund link and a claim receipt are never the same money
(the refund link refuses a receipt), so nothing counts twice. *Yours* is what is left after both, never below zero.
The transaction page shows one purchase; the Budget category sheet shows the month's purchases in its categories.
"""

from __future__ import annotations

from decimal import Decimal

from lightning.core.money import ZERO

FIGURES = ("paid", "returned", "expected", "yours")


class ExpenseRecoveries:
    def __init__(self, db, reimbursements, refunds):
        self.db = db
        self.reimbursements = reimbursements  # ReimbursementService: the claims' own figures
        self.refunds = refunds  # RefundLinkService: refunds that name the purchase

    def of(self, expense_id: int) -> dict | None:
        """The four figures for one purchase, or None when nothing came back or is expected."""
        claims = self.reimbursements.recovery(expense_id)
        refunded = sum((row["amount"] for row in self.refunds.refunds_of(expense_id) if row["status"] == "POSTED"), ZERO)
        returned = claims["received"] + refunded
        if not returned and not claims["expected"]:
            return None
        paid = claims["paid"]
        return {"paid": paid, "returned": returned, "expected": claims["expected"],
                "yours": max(paid - returned - claims["expected"], ZERO)}

    def for_categories(self, category_ids, start, end) -> dict | None:
        """The four figures summed over the purchases dated in the period that have money back or expected, each
        counted at its share in these categories; None when there are none."""
        wanted = sorted({int(cid) for cid in category_ids})
        if not wanted:
            return None
        marks = ",".join("?" * len(wanted))
        rows = self.db.all(
            "SELECT t.id,SUM(CASE WHEN le.category_id IN (" + marks + ") THEN -le.amount_base_e6 ELSE 0 END) here_e6,"
            "SUM(-le.amount_base_e6) all_e6 FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            "JOIN financial_assets a ON a.id=le.asset_id "
            "WHERE t.type='OUT' AND t.status='POSTED' AND t.date BETWEEN ? AND ? AND a.is_cash=1 "
            "AND le.effect='OUTFLOW' AND le.owner_id IS NULL "
            "AND (t.id IN (SELECT expense_id FROM reimbursement_claims WHERE expense_id IS NOT NULL) "
            "OR t.id IN (SELECT expense_id FROM refund_links)) GROUP BY t.id HAVING here_e6>0 ORDER BY t.date,t.id",
            (*wanted, str(start)[:10], str(end)[:10]))
        totals = {key: ZERO for key in FIGURES}
        count = 0
        for row in rows:
            figures = self.of(int(row["id"]))
            if figures is None:
                continue
            share = Decimal(int(row["here_e6"])) / Decimal(int(row["all_e6"])) if int(row["all_e6"]) else Decimal(1)
            for key in FIGURES:
                totals[key] += figures[key] * share
            count += 1
        if not count:
            return None
        return {**{key: value.quantize(Decimal("0.01")) for key, value in totals.items()}, "count": count}
