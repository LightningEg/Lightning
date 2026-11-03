-- IT-9K: the checked-month refusal carries a code, so the database layer matches the code, not the English sentence.
-- Same five triggers as 0056, only the message differs: the sentence people read, then its code [LN-E0001].
DROP TRIGGER checked_ledger_insert;
DROP TRIGGER checked_ledger_update;
DROP TRIGGER checked_ledger_delete;
DROP TRIGGER checked_transaction_update;
DROP TRIGGER checked_transaction_delete;
CREATE TRIGGER checked_ledger_insert BEFORE INSERT ON ledger_entries
WHEN EXISTS(SELECT 1 FROM reconciled_through r WHERE r.account_id=NEW.account_id AND NEW.date<=r.date)
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
CREATE TRIGGER checked_ledger_update BEFORE UPDATE ON ledger_entries
WHEN EXISTS(SELECT 1 FROM reconciled_through r WHERE (r.account_id=OLD.account_id AND OLD.date<=r.date)
    OR (r.account_id=NEW.account_id AND NEW.date<=r.date))
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
CREATE TRIGGER checked_ledger_delete BEFORE DELETE ON ledger_entries
WHEN EXISTS(SELECT 1 FROM reconciled_through r WHERE r.account_id=OLD.account_id AND OLD.date<=r.date)
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
CREATE TRIGGER checked_transaction_update BEFORE UPDATE ON transactions
WHEN EXISTS(SELECT 1 FROM ledger_entries le JOIN reconciled_through r ON r.account_id=le.account_id
    WHERE le.transaction_id=OLD.id AND le.date<=r.date)
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
CREATE TRIGGER checked_transaction_delete BEFORE DELETE ON transactions
WHEN EXISTS(SELECT 1 FROM ledger_entries le JOIN reconciled_through r ON r.account_id=le.account_id
    WHERE le.transaction_id=OLD.id AND le.date<=r.date)
BEGIN SELECT RAISE(ABORT,'This month was checked against the bank. Unlock it first. [LN-E0001]'); END;
