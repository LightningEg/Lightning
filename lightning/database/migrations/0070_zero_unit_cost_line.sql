-- NF-5A4: a return of capital posts a line of zero units that only lowers a holding's cost (owner decision 2026-11-02).
-- ledger_entries is rebuilt the way 0013 rebuilt it: every column and row copied unchanged, only the zero-quantity CHECK
-- is relaxed for one kind of line (INTERNAL, cost falling). The indexes, the two views, the reserve-link trigger and the
-- five checked-month triggers that point at the table are recreated exactly as they were (0056, 0069).
DROP VIEW IF EXISTS v_ledger;
DROP VIEW IF EXISTS v_balances;
DROP TRIGGER IF EXISTS tr_ledger_edit_clears_reserve_links;
DROP TRIGGER checked_ledger_insert;
DROP TRIGGER checked_ledger_update;
DROP TRIGGER checked_ledger_delete;
DROP TRIGGER checked_transaction_update;
DROP TRIGGER checked_transaction_delete;
DROP INDEX IF EXISTS ix_ledger_account_date;
DROP INDEX IF EXISTS ix_ledger_asset_date;
DROP INDEX IF EXISTS ix_ledger_category_date;
DROP INDEX IF EXISTS ix_ledger_transaction;
DROP INDEX IF EXISTS ix_ledger_account_cleared;
DROP INDEX IF EXISTS ix_ledger_owner_balance;
ALTER TABLE ledger_entries RENAME TO ledger_entries_before_zero_unit;
CREATE TABLE ledger_entries (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    line_no INTEGER NOT NULL,
    date TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    asset_id INTEGER NOT NULL REFERENCES financial_assets(id),
    quantity_e6 INTEGER NOT NULL,
    unit_price_e6 INTEGER NOT NULL,
    amount_e6 INTEGER NOT NULL,
    fx_rate_e6 INTEGER NOT NULL,
    amount_base_e6 INTEGER NOT NULL,
    effect TEXT NOT NULL CHECK (effect IN ('INFLOW','OUTFLOW','INTERNAL','OPENING','REVALUATION')),
    category_id INTEGER REFERENCES categories(id),
    memo TEXT NOT NULL DEFAULT '', cleared INTEGER NOT NULL DEFAULT 0 CHECK (cleared IN (0, 1)), owner_id INTEGER REFERENCES counterparties(id),
    UNIQUE(transaction_id,line_no),
    CHECK (effect='REVALUATION' OR quantity_e6<>0 OR (effect='INTERNAL' AND amount_e6<0)),
    CHECK (effect NOT IN ('INFLOW','OUTFLOW') OR category_id IS NOT NULL)
);
INSERT INTO ledger_entries(id,transaction_id,line_no,date,account_id,asset_id,quantity_e6,unit_price_e6,
                           amount_e6,fx_rate_e6,amount_base_e6,effect,category_id,memo,cleared,owner_id)
SELECT id,transaction_id,line_no,date,account_id,asset_id,quantity_e6,unit_price_e6,amount_e6,fx_rate_e6,
       amount_base_e6,effect,category_id,memo,cleared,owner_id FROM ledger_entries_before_zero_unit;
CREATE TEMP TABLE _zero_unit_copy_check(ok INTEGER CHECK(ok=1));
INSERT INTO _zero_unit_copy_check SELECT
    (SELECT COUNT(*) FROM ledger_entries_before_zero_unit)=(SELECT COUNT(*) FROM ledger_entries);
DROP TABLE _zero_unit_copy_check;
DROP TABLE ledger_entries_before_zero_unit;
CREATE INDEX ix_ledger_account_date ON ledger_entries(account_id,date);
CREATE INDEX ix_ledger_asset_date ON ledger_entries(asset_id,date);
CREATE INDEX ix_ledger_category_date ON ledger_entries(category_id,date);
CREATE INDEX ix_ledger_transaction ON ledger_entries(transaction_id);
CREATE INDEX ix_ledger_account_cleared ON ledger_entries(account_id, cleared, date);
CREATE INDEX ix_ledger_owner_balance ON ledger_entries(account_id, asset_id, owner_id, date);

CREATE VIEW v_ledger AS
SELECT t.ref || '/' || le.line_no AS line_ref,le.date AS date,t.type AS type,t.status AS status,
       a.code || ' · ' || a.name AS account,fa.code AS asset,
       printf('%.6f',le.quantity_e6/1000000.0) AS quantity,
       printf('%.2f',le.amount_e6/1000000.0) AS amount,fa.currency AS currency,
       printf('%.2f',le.amount_base_e6/1000000.0) AS amount_base,le.effect AS effect,
       CASE WHEN c.id IS NULL THEN '' ELSE c.code || ' · ' || c.name END AS category,
       t.description AS description,t.counterparty AS counterparty
FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id
JOIN accounts a ON a.id=le.account_id JOIN financial_assets fa ON fa.id=le.asset_id
LEFT JOIN categories c ON c.id=le.category_id;
CREATE VIEW v_balances AS
SELECT a.code || ' · ' || a.name AS account,fa.code AS asset,
       printf('%.2f',SUM(le.quantity_e6)/1000000.0) AS balance,fa.currency AS currency
FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id AND t.status='POSTED'
JOIN accounts a ON a.id=le.account_id JOIN financial_assets fa ON fa.id=le.asset_id
GROUP BY a.id,fa.id;

CREATE TRIGGER tr_ledger_edit_clears_reserve_links
AFTER DELETE ON ledger_entries
BEGIN
    DELETE FROM reserve_transaction_links WHERE transaction_id=OLD.transaction_id;
END;
CREATE TRIGGER checked_ledger_insert BEFORE INSERT ON ledger_entries
WHEN EXISTS(SELECT 1 FROM reconciled_through r WHERE r.account_id=NEW.account_id AND NEW.date<=r.date)
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
CREATE TRIGGER checked_ledger_update BEFORE UPDATE ON ledger_entries
WHEN EXISTS(SELECT 1 FROM reconciled_through r WHERE (r.account_id=OLD.account_id AND OLD.date<=r.date)
    OR (r.account_id=NEW.account_id AND NEW.date<=r.date))
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
CREATE TRIGGER checked_ledger_delete BEFORE DELETE ON ledger_entries
WHEN EXISTS(SELECT 1 FROM reconciled_through r WHERE r.account_id=OLD.account_id AND OLD.date<=r.date)
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
CREATE TRIGGER checked_transaction_update BEFORE UPDATE ON transactions
WHEN EXISTS(SELECT 1 FROM ledger_entries le JOIN reconciled_through r ON r.account_id=le.account_id
    WHERE le.transaction_id=OLD.id AND le.date<=r.date)
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
CREATE TRIGGER checked_transaction_delete BEFORE DELETE ON transactions
WHEN EXISTS(SELECT 1 FROM ledger_entries le JOIN reconciled_through r ON r.account_id=le.account_id
    WHERE le.transaction_id=OLD.id AND le.date<=r.date)
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
