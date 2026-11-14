-- NF-12AK2: leave one transaction out of estimates (owner, 2026-11-13). A row marks an expense that budget averages
-- and Fill skip, with every refund or claim receipt linked to it; Cash and Spent still count it. Optional, never
-- automatic. Category exclusions (budget_one_off_exclusions) stay as they are. Marks a transaction; never posts.
CREATE TABLE budget_estimate_exclusions (
    transaction_id  INTEGER NOT NULL PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
