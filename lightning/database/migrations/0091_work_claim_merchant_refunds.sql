-- BT-12AR. A linked merchant refund lowers the net purchase cost for a work claim.
-- Allocate the valid linked amount against the personal share first, then against the expected employer share.
DROP VIEW work_claim_allocations;

CREATE VIEW work_claim_refund_lines AS
WITH work_expenses AS (
    SELECT rc.id claim_id,t.id expense_id,t.date expense_date,
           MAX(0,SUM(-le.amount_base_e6)-rc.expected_e6) personal_e6,
           MIN(SUM(-le.amount_base_e6),rc.expected_e6) work_capacity_e6
    FROM reimbursement_claims rc JOIN transactions t ON t.id=rc.expense_id
    JOIN ledger_entries le ON le.transaction_id=t.id JOIN financial_assets a ON a.id=le.asset_id
    WHERE rc.paid_for_work=1 AND t.status='POSTED' AND t.type='OUT' AND a.is_cash=1
      AND le.effect='OUTFLOW' AND le.amount_base_e6<0 AND le.category_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM ledger_entries x WHERE x.transaction_id=t.id AND x.owner_id IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM money_from_others m WHERE m.transaction_id=t.id)
    GROUP BY rc.id
), refund_rows AS (
    SELECT e.claim_id,e.personal_e6,e.work_capacity_e6,le.transaction_id,le.line_no,le.category_id,le.date,
           le.amount_base_e6 capacity,rl.amount_e6
    FROM work_expenses e JOIN refund_links rl ON rl.expense_id=e.expense_id
    JOIN transactions t ON t.id=rl.refund_id
    JOIN ledger_entries le ON le.transaction_id=t.id JOIN financial_assets a ON a.id=le.asset_id
    JOIN categories c ON c.id=le.category_id
    WHERE t.status='POSTED' AND t.type='IN' AND t.date>=e.expense_date AND a.is_cash=1
      AND le.owner_id IS NULL AND le.effect='OUTFLOW' AND le.amount_base_e6>0
      AND c.movement='OUTFLOW' AND c.is_system=0
      AND NOT EXISTS (SELECT 1 FROM money_from_others m WHERE m.transaction_id=t.id)
      AND NOT EXISTS (SELECT 1 FROM reimbursement_receipts rr WHERE rr.receipt_id=t.id)
      AND EXISTS (SELECT 1 FROM ledger_entries x JOIN financial_assets xa ON xa.id=x.asset_id
                  WHERE x.transaction_id=e.expense_id AND x.category_id=le.category_id
                  AND xa.is_cash=1 AND x.effect='OUTFLOW' AND x.amount_base_e6<0)
), linked AS (
    SELECT *, MIN(capacity, MAX(0, amount_e6 - (SUM(capacity) OVER (
        PARTITION BY transaction_id ORDER BY category_id,line_no) - capacity))) linked_e6
    FROM refund_rows
), running AS (
    SELECT *, SUM(linked_e6) OVER (PARTITION BY claim_id ORDER BY date,transaction_id,category_id,line_no) refunded_e6
    FROM linked
)
SELECT claim_id,transaction_id,line_no,category_id,date,linked_e6,
       MAX(0, MIN(refunded_e6-personal_e6,work_capacity_e6)
           - MAX(0,refunded_e6-linked_e6-personal_e6)) work_e6
FROM running;

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
        COALESCE((SELECT SUM(r.covered) FROM receipt_lines r WHERE r.claim_id=e.claim_id),0)
        + COALESCE((SELECT SUM(r.work_e6) FROM work_claim_refund_lines r WHERE r.claim_id=e.claim_id),0)) END covered
    FROM expenses e
)
SELECT claim_id,transaction_id,line_no,category_id,date,'receipt' kind,covered amount_e6 FROM receipt_lines
UNION ALL
SELECT claim_id,transaction_id,line_no,category_id,date,'expense',
       -MIN(capacity,MAX(0,covered + capacity - SUM(capacity) OVER (PARTITION BY transaction_id ORDER BY line_no)))
FROM expense_lines
UNION ALL
SELECT claim_id,transaction_id,line_no,category_id,date,'refund',work_e6
FROM work_claim_refund_lines
WHERE work_e6>0;
