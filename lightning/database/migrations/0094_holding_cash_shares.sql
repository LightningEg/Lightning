-- NF-7AU: a dated share of one account's investment can count toward Free cash.
CREATE TABLE holding_cash_shares (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES financial_assets(id) ON DELETE CASCADE,
    effective_on TEXT NOT NULL,
    percent_bps INTEGER CHECK(percent_bps BETWEEN 0 AND 10000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, asset_id, effective_on)
);
