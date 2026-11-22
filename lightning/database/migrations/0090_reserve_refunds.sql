-- NF-12AK4 (owner, 2026-11-13): a refund that names a reserve-funded purchase goes back to that reserve first.
-- Refunds fill the purchase's reserve-funded part in date order, and each reserve's share in link order; what is
-- beyond the reserve-funded part reduces monthly-plan spending as before. A read-only view: nothing is posted.
CREATE VIEW reserve_refunds AS
WITH funded AS (
    SELECT l.reserve_id, l.transaction_id expense_id, l.amount_e6,
           SUM(l.amount_e6) OVER (PARTITION BY l.transaction_id ORDER BY l.id) - l.amount_e6 before_e6
    FROM reserve_transaction_links l JOIN transactions t ON t.id=l.transaction_id WHERE t.status='POSTED'
), back AS (
    SELECT rl.refund_id, rl.expense_id, rl.amount_e6, r.date,
           SUM(rl.amount_e6) OVER (PARTITION BY rl.expense_id ORDER BY r.date, rl.refund_id) - rl.amount_e6 before_e6
    FROM refund_links rl JOIN transactions r ON r.id=rl.refund_id JOIN transactions e ON e.id=rl.expense_id
    WHERE r.status='POSTED' AND e.status='POSTED'
      AND NOT EXISTS (SELECT 1 FROM reimbursement_receipts x WHERE x.receipt_id=rl.refund_id)
), shares AS (
    SELECT f.reserve_id, b.refund_id, b.expense_id, b.date,
           MIN(b.before_e6 + b.amount_e6, f.before_e6 + f.amount_e6) - MAX(b.before_e6, f.before_e6) amount_e6
    FROM back b JOIN funded f ON f.expense_id=b.expense_id
)
SELECT reserve_id, refund_id, expense_id, date, amount_e6 FROM shares WHERE amount_e6 > 0;

-- What each reserve has paid out, net of refunds that came back to it, dated by the movement.
CREATE VIEW reserve_spending AS
SELECT l.reserve_id, l.transaction_id, t.date, l.amount_e6
FROM reserve_transaction_links l JOIN transactions t ON t.id=l.transaction_id WHERE t.status='POSTED'
UNION ALL
SELECT reserve_id, refund_id, date, -amount_e6 FROM reserve_refunds;
