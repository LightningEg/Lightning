---
title: Stale code - about 25 unused or test-only functions, two settings no one reads, and legacy rows no one writes
type: tech
area: architecture
status: ready
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 3](../../reports/audit-3.md) §3. Each name was searched in `lightning/`, `tests/`, `tools/`, `android/`, the
templates and the journal's command strings. Recheck each one before deleting it.

- **Unused:**
  - `ui/keynotes.py`: `lowest_point`, `next_payment`, `largest_part`, `sale_cost`, `cash_share`
  - `ui/visuals.py`: `flow_trend`, `spending_bars`, `portfolio_trend`
  - `workflows/review.py`: `for_page`
  - `MoneyFromOthersService.transaction_owner`
  - `AccountService.get_by_code` and `AccountRepository.get_by_code`
  - `budgeting/domain.used_pct`
  - `investments/domain.unrealized_pct` and `variance_per_unit`
  - `core/codes.SEGMENT_RE`
- **Only tests call them** (delete each with its test, or give it a caller):
  - `ReportingService.monthly_trend`, `bridge_for_month`, `foreign_currency_accounts`
  - `TransactionService.set_transaction_owner`, `counterparty_suggestions` (with `repo.counterparty_categories`)
  - `reserves.allocation_at`, `Position.deposits_after_sale`
  - `dashboard._owned_wealth_rows`, `migrator.pending_migrations`
  - `conversion.rebuild_trade_rates`. Architecture calls it the repair path: give it a caller in the integrity screen, or say in Architecture that it is test-only.
- **Settings and flags:**
  - `budget_carryover_month` is written (`ui/routes/budget.py:540`) and never read.
  - `weekly_review_remaining` (`workflows/weekly.py:30`) is read only by a test.
  - `market_url` is set only by tests.
  - `allow_foreign` is always on (`accounts/service.py:105`), and its message still says other currencies are "not built yet".
- **Leftovers:** imports repeated inside functions (`assets/service.py:214,235`), the `"owner_id" in row.keys()` check (`transactions/repository.py:33`), and the `transactions_fts` exclusion in `undo.py`.
- **Legacy mode (owner decision):** `python -m lightning` still opens a plaintext `data/lightning.db`. Code that exists only for it:
  - `live_prices.fetch_if_due`
  - the browser branch of `ui/routes/settings.py:247-266`
  - the legacy filename rule at `bootstrap.py:134`

  If the owner agrees, limit legacy mode to `--demo` and `--sample`.

## Fix
One branch. Delete, run the full suite, and check `python -m lightning.core.figures` and `tools/issues.py --check`.
