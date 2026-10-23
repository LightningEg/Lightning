-- Audit 3, 9I: each of these repeats the leading columns of another index or unique constraint on the same table,
-- which answers every lookup it could, so it only slowed writes and grew the file.
-- ix_ledger_transaction (transaction_id)                       = UNIQUE(transaction_id, line_no)
-- ix_price_asset_date (asset_id, date)                         = UNIQUE(asset_id, date, source)
-- ix_other_asset_valuations_account_date (account_id, effective_date) = UNIQUE(account_id, effective_date)
-- ix_budgets_category_month (category_id, month)               = UNIQUE(category_id, month, one_off)
-- ix_budget_carryover_resets_month (category_id, month)        = PRIMARY KEY(category_id, month)
DROP INDEX IF EXISTS ix_ledger_transaction;
DROP INDEX IF EXISTS ix_price_asset_date;
DROP INDEX IF EXISTS ix_other_asset_valuations_account_date;
DROP INDEX IF EXISTS ix_budgets_category_month;
DROP INDEX IF EXISTS ix_budget_carryover_resets_month;
