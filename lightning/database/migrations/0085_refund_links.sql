-- NF-12AK3: a refund can name the purchase it returns, so estimates count the money back in the purchase's month
-- (owner, 2026-11-13). A link annotates two existing transactions; it never posts or changes ledger entries.
-- A refund names at most one purchase; a purchase can have several refunds, together never more than its net.
CREATE TABLE refund_links (
    id              INTEGER PRIMARY KEY,
    refund_id       INTEGER NOT NULL UNIQUE REFERENCES transactions(id) ON DELETE CASCADE,
    expense_id      INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    amount_e6       INTEGER NOT NULL CHECK (amount_e6 > 0),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    CHECK (refund_id <> expense_id)
);
CREATE INDEX ix_refund_links_expense ON refund_links(expense_id, id);
