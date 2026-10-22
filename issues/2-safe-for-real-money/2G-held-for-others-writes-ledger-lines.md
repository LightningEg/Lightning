---
title: Marking money as held for someone writes ledger lines itself - six-decimal base amounts block undo, and a voided sale still counts
type: bug
area: transactions
status: ready
created: 2026-10-21
by: Claude
skills: number-audit
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
Found by [Audit 4](../../reports/audit-4.md) §2. Severity: high (stored money breaks a posting rule, and undo is refused).

1. `money_from_others.py:20-57` (`_tag_exact_line`) and `ownership_migration.py:60-80` UPDATE and INSERT `ledger_entries`
   directly, outside `TransactionService`: no `validate_posting`, no audit. A part-tag splits the base amount by integer division
   in micro-units. Reproduced on a temporary profile: 100.01 USD in at 50.123457, then 33.33 marked as Dad's. The stored base
   amounts are 3342.234157 and 1670.615843. Any later undo on that transaction is refused: "Line 1: amount_base has more than
   2 decimal places" (from `bootstrap.validate_history`).
2. `money_from_others.py:206-210` sums `investment_custody_events` without `t.status='POSTED'` (the next check, line 213, has
   it). Reproduced: buy 10 units for Dad, sell 10, void the sale. The ledger says Dad holds 10.00, but selling 5 is refused:
   "There are not enough units owned by Dad".
3. Behind both: who owns what is kept twice, in the ledger's `owner_id` and in `investment_custody_events`.
   `_validate_owner_partition` (line 58) is a second copy of `TransactionService._validate_owner_balances`.

## Fix
- Move tagging into `TransactionService` as a repost. Round each base amount to 2 places and give the remainder to the other line.
- Check custody against the ledger's `owner_id` only.
- Stop writing `investment_custody_events`, and drop the legacy `transaction_id IS NULL` reads (nothing writes those rows now).
- Tests: the two reproductions above.
