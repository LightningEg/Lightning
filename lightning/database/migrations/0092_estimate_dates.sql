-- NF-12AK: only explicit estimate dates are stored. Automatic recovery dates follow their purchase.
CREATE TABLE budget_estimate_dates (
    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    estimate_date TEXT NOT NULL
);
ALTER TABLE refund_links ADD COLUMN estimate_date_override TEXT;
ALTER TABLE reimbursement_receipts ADD COLUMN estimate_date_override TEXT;
