ALTER TABLE cash_reserves ADD COLUMN planned_item_id INTEGER REFERENCES planned_items(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX one_active_reserve_per_bill ON cash_reserves(planned_item_id)
WHERE planned_item_id IS NOT NULL AND status='ACTIVE';
ALTER TABLE reserve_allocation_history ADD COLUMN planned_item_id INTEGER REFERENCES planned_items(id) ON DELETE SET NULL;
CREATE INDEX ix_reserve_history_bill_day ON reserve_allocation_history(effective_date)
WHERE planned_item_id IS NOT NULL;
ALTER TABLE reserve_transaction_links ADD COLUMN planned_item_id INTEGER REFERENCES planned_items(id) ON DELETE SET NULL;
CREATE INDEX ix_reserve_payment_bill ON reserve_transaction_links(planned_item_id,transaction_id)
WHERE planned_item_id IS NOT NULL;
