-- IV-3H7 (owner, 2026-11-08: "optional loan rate yes"): a loan may carry its annual interest rate and how it is
-- charged, FLAT (on the amount borrowed for the whole term) or REDUCING (on the balance still owed). Both stay empty
-- for every existing row and for bills, subscriptions and income. Nothing in the ledger changes: payments stay spending;
-- the rate only lets the Loans tab show the total interest and the cost of the loan.
ALTER TABLE planned_items ADD COLUMN interest_rate_e6 INTEGER CHECK (interest_rate_e6 IS NULL OR interest_rate_e6 BETWEEN 0 AND 100000000);
ALTER TABLE planned_items ADD COLUMN rate_kind TEXT CHECK (rate_kind IS NULL OR rate_kind IN ('FLAT','REDUCING'));
