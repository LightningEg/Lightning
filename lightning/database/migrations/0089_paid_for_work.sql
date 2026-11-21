-- NF-12AM. Explicit work advances and their settlement are a personal reporting overlay.
ALTER TABLE reimbursement_claims ADD COLUMN paid_for_work INTEGER NOT NULL DEFAULT 0 CHECK(paid_for_work IN (0,1));
ALTER TABLE reimbursement_claims ADD COLUMN work_closed_on TEXT;

-- Allocate only the covered part of each owned cash line. On split purchases use line order;
-- on split deposits use the original expense categories first, leaving salary in income.
CREATE VIEW work_claim_allocations AS
WITH expenses AS (
    SELECT rc.id claim_id, rc.expected_e6, rc.work_closed_on, le.transaction_id, le.line_no,
           le.category_id, le.date, -le.amount_base_e6 capacity
    FROM reimbursement_claims rc JOIN transactions t ON t.id=rc.expense_id
    JOIN ledger_entries le ON le.transaction_id=t.id JOIN financial_assets a ON a.id=le.asset_id
    WHERE rc.paid_for_work=1 AND t.status='POSTED' AND t.type='OUT' AND a.is_cash=1
      AND le.effect='OUTFLOW' AND le.amount_base_e6<0 AND le.category_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM ledger_entries x WHERE x.transaction_id=t.id AND x.owner_id IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM money_from_others m WHERE m.transaction_id=t.id)
), receipts AS (
    SELECT rr.claim_id, rr.amount_e6, le.transaction_id, le.line_no, le.category_id, le.date,
           le.amount_base_e6 capacity,
           CASE WHEN EXISTS (SELECT 1 FROM expenses e WHERE e.claim_id=rr.claim_id AND e.category_id=le.category_id)
                THEN 0 ELSE 1 END priority
    FROM reimbursement_receipts rr JOIN transactions t ON t.id=rr.receipt_id
    JOIN ledger_entries le ON le.transaction_id=t.id JOIN financial_assets a ON a.id=le.asset_id
    JOIN categories c ON c.id=le.category_id
    WHERE EXISTS (SELECT 1 FROM expenses e WHERE e.claim_id=rr.claim_id)
      AND t.type='IN' AND t.status='POSTED' AND a.is_cash=1 AND le.owner_id IS NULL
      AND le.effect IN ('INFLOW','OUTFLOW') AND le.amount_base_e6>0 AND c.code<>'EXP.SYSTEM.CUSTODY'
), receipt_lines AS (
    SELECT *, MIN(capacity, MAX(0, amount_e6 + capacity -
        SUM(capacity) OVER (PARTITION BY transaction_id ORDER BY priority,line_no))) covered
    FROM receipts
), expense_lines AS (
    SELECT *, CASE WHEN work_closed_on IS NULL THEN expected_e6 ELSE MIN(expected_e6,
        COALESCE((SELECT SUM(r.covered) FROM receipt_lines r WHERE r.claim_id=e.claim_id),0)) END covered
    FROM expenses e
)
SELECT claim_id,transaction_id,line_no,category_id,date,1 is_receipt,covered amount_e6 FROM receipt_lines
UNION ALL
SELECT claim_id,transaction_id,line_no,category_id,date,0,
       -MIN(capacity,MAX(0,covered + capacity - SUM(capacity) OVER (PARTITION BY transaction_id ORDER BY line_no)))
FROM expense_lines;
