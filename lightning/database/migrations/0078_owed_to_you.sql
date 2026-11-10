-- NF-12G2: money lent to a person (owner 2026-11-08). One RECEIVABLE "Owed to you" account per person (the accounts
-- CHECK list allows RECEIVABLE since 0053); its cash sits in the asset class RECEIVABLE. The link says whose account
-- it is. Lending and repayment are transfers, forgiving is spending; nothing here posts money.
INSERT OR IGNORE INTO asset_classes(code, name, parent_id, sort_order, created_at, updated_at)
SELECT 'RECEIVABLE', 'Owed to you', NULL, COALESCE((SELECT MAX(sort_order) FROM asset_classes), 0) + 1,
       strftime('%Y-%m-%dT%H:%M:%S', 'now'), strftime('%Y-%m-%dT%H:%M:%S', 'now');

CREATE TABLE owed_to_you_accounts (
    account_id      INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    counterparty_id INTEGER NOT NULL UNIQUE REFERENCES counterparties(id) ON DELETE RESTRICT,
    created_at      TEXT NOT NULL
);
