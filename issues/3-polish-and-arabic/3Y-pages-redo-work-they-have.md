---
title: Pages redo work they already did - a read opens a write transaction that empties the request cache
type: tech
area: performance
status: ready
created: 2026-10-21
by: Claude
skills: perf-check
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
Found by [Audit 3](../../reports/audit-3.md) §1. Nothing a person sees changes; pages get faster and stop taking the write lock.

1. **An empty write transaction on every read of today.**
   - `PositionService._at` (`planning/position.py:348`) calls `planning.match_payments(today)`.
   - `match_payments` (`planning/service.py:245`) always opens `db.transaction()`, even when nothing settles.
   - `undo.begin` and `undo.finish` then write their housekeeping. `total_changes` moves, and `core/memo.py:37` empties the cache.
   - `ui/routes/planning.py:193,224` do the same on GET.
   - The middleware already matches payments after every write (`ui/web.py:429`).
   - Measured, identical HTML: Overview 705 → 445 SELECTs, Cash planning 480 → 263, Investments 290 → 155.
2. **Repeated reads with no cache.** Calls per Overview against distinct arguments:
   - `BudgetService.month_view` 19/5
   - `plan_summary` 6/3
   - `income_average` 4/1
   - `ReportingService.cash_flow` 28/10
   - `CategoryService.get_by_code` 41/20
   - `PlanningService.items` 86/6

   `own_liquidation_factors` and `certificate_for_asset` run once per date, though neither depends on it.
3. **Every Arabic page embeds the whole browser translation table** (2,694 entries, `ui/web.py:362`): the Overview is 48 KB in English and 500 KB in Arabic.

## Fix
1. Return early from `match_payments` when nothing is to be settled, and skip `undo.finish` housekeeping when the group recorded nothing. Drop the GET-time calls.
2. Add `@request_cached(deep=True)` to the reads above.
3. Serve the table as a cached static script.

Keep `tests/test_reporting_performance.py` comparing cached and uncached HTML, and lower `PAGE_READ_BUDGET`.
