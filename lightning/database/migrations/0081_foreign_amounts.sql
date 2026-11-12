-- NF-7AK3: a purchase in another currency on a pound account (owner 2026-11-09/11). The ledger keeps pounds (cash
-- sits only in an account of its own currency); this row keeps what the person paid in the shop's currency beside
-- it. The entry holds the pound equivalent at the dated rate until the bank's pound debit settles it (settled=1),
-- then that debit's amount: one expense, never two. Written only by lightning/foreign_amounts.py.
CREATE TABLE foreign_amounts (
    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    currency       TEXT NOT NULL CHECK (length(currency) = 3 AND currency = upper(currency)),
    amount_e6      INTEGER NOT NULL CHECK (amount_e6 > 0),
    settled        INTEGER NOT NULL DEFAULT 0 CHECK (settled IN (0, 1)),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
