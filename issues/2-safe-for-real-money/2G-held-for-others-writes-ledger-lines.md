---
title: Who owns what is recorded twice - the ledger's owner and investment_custody_events - and tagging writes ledger lines itself
type: tech
area: transactions
status: ready
created: 2026-10-21
by: Claude
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
Found by [Audit 4](../../reports/audit-4.md) §2. Its two money bugs are fixed: 2G1 (a part-tag stored six-decimal
base amounts, so every later undo was refused) and 2G2 (a voided sale still counted against the owner's next sale). They are
covered by `tests/test_money_from_others_flow.py`. What is left is the structure behind them.

## 2G3 One record of who owns what
- `money_from_others.py` (`_tag_exact_line`) and `ownership_migration.py` still UPDATE and INSERT `ledger_entries` directly, outside `TransactionService`. That means no audit and no `validate_posting` at write time. The split itself now passes it (`core/ledger.split_line_e6`).
- `investment_custody_events` repeats the ledger's `owner_id`. The ledger check (`TransactionService._validate_owner_balances`) already refuses a sale of units someone does not hold. `_validate_owner_partition` is a second copy of it.
- Nothing writes `money_from_others` rows without a transaction any more. `cash_balance`, `cash_total_for_account`, `totals_by_account`, `by_owner` and `history` still read them (see 9L).

## Fix
- Move tagging into `TransactionService` as a repost.
- Read investment custody history from the ledger's `owner_id`, then stop writing `investment_custody_events`.
- Drop the legacy reads.
- Tests: the existing custody, zakat and investment tests stay green, and the investment history shows the same rows.
