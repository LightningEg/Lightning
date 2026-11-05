-- What a flat, house, plot or car adds to an Other asset account (NF-9C): its kind, what it cost and when, and the loan
-- that paid for it. The dated values stay in other_asset_valuations.
CREATE TABLE other_asset_details (
    account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'other' CHECK (kind IN ('flat','house','land','car','other')),
    purchase_date TEXT,
    purchase_price_e6 INTEGER CHECK (purchase_price_e6 IS NULL OR purchase_price_e6 >= 0),
    loan_item_id INTEGER REFERENCES planned_items(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX ix_other_asset_details_loan ON other_asset_details(loan_item_id) WHERE loan_item_id IS NOT NULL;
