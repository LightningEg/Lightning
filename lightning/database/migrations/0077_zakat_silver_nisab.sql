-- NF-9D6: the nisab basis (gold 85 g by default, silver 595 g, or the lower of the two; owner 2026-11-08) and the
-- silver gram price the user types with its date. Old profiles keep gold.
ALTER TABLE zakat_settings ADD COLUMN nisab_basis TEXT NOT NULL DEFAULT 'gold'
    CHECK (nisab_basis IN ('gold', 'silver', 'lower'));
ALTER TABLE zakat_settings ADD COLUMN typed_silver_e6 INTEGER CHECK (typed_silver_e6 IS NULL OR typed_silver_e6 > 0);
ALTER TABLE zakat_settings ADD COLUMN typed_silver_date TEXT;
