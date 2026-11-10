---
title: The import review asks four or more queries for every statement row - 1,136 for a 90-row file, about 12,000 for a year's statement
type: tech
pillar: capture
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
---

## Report
Found by [r33](../1-easy-to-contribute/r33-code-review-and-loose-ends/report.md) F4. Opening the sample's waiting review (`/accounts/1/import/1`, 90 rows) asks 1,136 queries in 322 ms. Per row, `lightning/bank_import_proposals.py:ImportProposals._preview` (line 59) asks:

| Times | Query | Where |
| --- | --- | --- |
| 360 (4 a row) | `SELECT 1 FROM bank_import_rows r JOIN bank_import_batches b ...` (reference seen before; same file imported before; voided earlier, two forms) | lines 94, 100, 234, 240 |
| 180 (2 a row) | `SELECT id FROM accounts WHERE active=1 AND lower(name)=lower(?)` | `_own_account` |
| 159 | `SELECT 1 FROM transactions t JOIN ledger_entries l ... WHERE t.status='POSTED' AND t.date ...` (already in the ledger) | same function |
| 159 | `SELECT code FROM accounts WHERE id=?` | |
| 159 | `SELECT DISTINCT le.account_id FROM ledger_entries le JOIN transactions t ...` | |

The count grows with the file, not with the profile. NF-7AB will rebuild the review screen but keeps these proposals.

## Fix
Files: `lightning/bank_import_proposals.py` only. One pull request per step; the review's HTML must not change.

## 9N1 Ask the account questions once · S
Do: `_own_account` and the `SELECT code FROM accounts WHERE id=?` read depend only on a name or an id. Before the `for row in rows:` loop build two dictionaries from one `SELECT id, code, lower(name) AS name FROM accounts WHERE active=1` (check the inactive case: the code read has no `active` filter, so load all accounts and filter in Python) and use them inside the loop. The file already does this once with `usual = functools.cache(self.transactions.usual_categories)`: follow that style.

## 9N2 Ask the "seen before" questions once · M
Do: before the loop, load three sets for this batch's account:
- posted or linked bank references of other batches: `SELECT r.bank_reference FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id JOIN transactions t ON t.id=r.transaction_id AND t.status='POSTED' WHERE b.account_id=? AND b.id<>? AND r.status IN ('POSTED','LINKED') AND r.bank_reference IS NOT NULL`;
- row numbers already posted from the same file (`b.file_hash=? OR b.file_hash LIKE ?`);
- voided references (the query of `_voided_earlier`'s first branch without the reference condition).
Replace the three per-row `self.db.scalar(...)` calls with `in` tests on those sets. Leave `_voided_earlier`'s second branch (no reference: date and amount) as it is.

Test for both: in `tests/test_bank_imports.py`, a review built from a fixture with a duplicate reference, a repeat of an earlier file and a voided earlier row still marks each row the same; then a test that counts queries for a 90-row preview and asserts fewer than 400 (pattern in `tests/test_reporting_performance.py`). Run `python -m pytest tests/test_bank_imports.py tests/test_import*.py -q` and Mohab.

## Done when
`/accounts/1/import/1` on the sample asks fewer than 400 queries with identical HTML, and the count no longer rises by four for each extra row. `Detail:` carries before and after. Release-note: `capture: reviewing a long bank statement opens faster.`
