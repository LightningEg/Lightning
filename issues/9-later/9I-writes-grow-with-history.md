---
title: Some writes and the reimbursements page do work that grows with the whole history
type: tech
area: performance
status: ready
created: 2026-10-21
by: Claude
skills: perf-check
---

## Report
Found by [Audit 3](../../reports/audit-3.md) §1. All of these are fast on today's profiles. Each grows with history, so fix it when the code is next touched.

1. **`_refuse_cash_below_zero`** (`transactions/service.py:472-517`) loads every cash line of the account and walks them in Python.
   - Its plan uses `ix_ledger_asset_date`, so it also scans other accounts' lines in the same currency.
   - One expense took 2.7 ms on the sample, 5.6 ms with 5,000 transfers elsewhere, and 20 ms with 5,000 more on the same account.
2. **`ReimbursementService.eligible_expenses`** (`reimbursements.py:116-131`) runs `_expense_capacity` for every posted expense: 1,846 statements for 265 expenses. `available_receipts` does the same for money in.
3. **One write runs the same checks twice.**
   - `post`, `repost` and `set_opening_balance` call `_validate_owner_balances`, then `_create`/`_update` call it again with the same arguments.
   - `_update` reads the transaction twice (lines 1050-1053).
   - `_create` and `_update` repeat the same 8-line counterparty block.
4. **`counterparties._link_historical`** (`counterparties.py:244-249`) normalises every unlinked transaction in Python on each create, alias or rename. Buys and sells are never linked, so they are rescanned forever: 5.9 ms became 32.6 ms with 5,000 of them.
5. **Small ones.**
   - `search_ids` builds full transactions and runs a COUNT just to return ids (9.6 ms against 0.9 ms).
   - `next_seq` uses `LIKE` over the ref index.
   - Five indexes repeat another: `ix_ledger_transaction`, `ix_price_asset_date`, `ix_other_asset_valuations_account_date`, `ix_budgets_category_month`, `ix_budget_carryover_resets_month`.

## Fix
1. One SQL sum for the balance before the day, then read only the days after it, using the account index.
2. One grouped query.
3. Validate once, in `_create`/`_update`.
4. Leave trade types out of the scan, or compare in SQL.
5. An ids-only query, a range query, and a migration that drops the five indexes.

Keep the outputs identical; the number-audit skill checks the figures.
