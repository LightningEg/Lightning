-- NF-7AU: protect a fixed amount in a holding and preserve earlier investment defaults.
ALTER TABLE holding_cash_shares ADD COLUMN protected_e6 INTEGER
    CHECK(protected_e6 IS NULL OR (protected_e6 >= 0 AND percent_bps IS NULL));
CREATE TABLE investment_cash_defaults (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES financial_assets(id) ON DELETE CASCADE,
    effective_on TEXT NOT NULL,
    counts INTEGER NOT NULL CHECK(counts IN (0,1)),
    UNIQUE(asset_id,effective_on)
);
