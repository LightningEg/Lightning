-- 0053 — the date an account was last checked against the bank; nothing on or before it can be edited.
CREATE TABLE reconciled_through (
    account_id INTEGER PRIMARY KEY REFERENCES accounts(id),
    date TEXT NOT NULL
);
