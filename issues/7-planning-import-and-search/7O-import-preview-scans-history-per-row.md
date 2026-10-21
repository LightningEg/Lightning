---
title: Bank-import review reads the whole transaction history once per row, so a 400-row statement takes 3 s to show
type: tech
area: import
status: ready
created: 2026-10-21
by: Claude
skills: perf-check
---

## Report
Found by [Audit 3](../../reports/audit-3.md) §1.
- `BankImportService._category_for` (`bank_imports.py:510`) calls `transactions.usual_categories()` for every row.
- That call is not cached and runs a window query over all posted transactions (`transactions/service.py:364`).
- In a profile with 400 rows, it took 1.78 s of the 2.94 s preview. Overall the preview averages about 8.5 queries per row (800 rows: 3.4 s).
- The preview runs on every review page load and again inside `confirm` (`bank_imports.py:578`).

## Fix
Compute `usual_categories()` once per preview, or mark it `@request_cached(deep=True)`. Test: the queries in one preview do not
grow with its row count beyond a fixed number per row.
