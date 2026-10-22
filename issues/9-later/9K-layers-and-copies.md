---
title: Structure - 18 modules outside the layer contract, and one fact kept in several places
type: tech
area: architecture
status: ready
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 4](../../reports/audit-4.md) §4.

1. **Layers the linter cannot see.**
   - These are in no `[tool.importlinter]` layer: `bank_imports`, `counterparties`, `demo`, `fx`, `integrity`, `money_from_others`, `ownership_migration`, `physical_items`, `reconciliation`, `reevaluations`, `reimbursements`, `reserves`, `samples`, `saved_views`, `sms_imports`, `undo`, `zakat`, and `lightning.sync`.
   - A contract that places them all breaks only once: `sync/transport.py:550 → runtime.paths`.
   - Upward calls the linter cannot see:
     - `bootstrap.py:193-207` wires budgeting to call planning: `budgets.scheduled_*`, `reserve_goal_needs`, and `savings_rate` reading health.
     - `database/connection.py:169` imports `lightning.undo`, and line 137 matches a trigger's message text.
   - `bootstrap.validate_history` (`bootstrap.py:253-304`) is ledger checking that calls private `TransactionService` methods.
2. **Copies of one fact.**
   - Four checks that a balance never goes below zero: `_validate_owner_balances`, `_refuse_cash_below_zero`, `_validate_owner_partition` (see 2G), `lowest_running_quantity`.
   - Two kinds of money rounding: `core/ledger._round2` rounds half to even and `core/money.quantize` rounds half up, so 10.01 × 50.5 posts 505.50 but quantizes to 505.51.
   - Four copies of the id check: `reserves._id`, `reimbursements._id`, `planning/service._id`, `workflows/activity._id`.
   - `MoneyFromOthersService` builds `CounterpartyService(self.db)` itself instead of getting it from `bootstrap`.
3. **Two startup paths.**
   - Legacy `main.py:100` always runs `reevaluations.process_due()`.
   - A profile open (`session._fill_prices`) reaches it only through a price-file fill, and swallows any failure without a log (`session.py:187`).
   - With no `market.zip`, a profile opened on 2026-12-05 posted 0 month-end checkpoints where `process_due` posted 10.
4. **Shape.**
   - `runtime/app.py:profile_app` is one 746-line function of nested routes.
   - There are 233 function-local imports across 59 modules; only three real cycles need them.
   - `budgeting/service.py:235` catches every exception while expanding one-off categories; narrow it to `NotFoundError`.

## Fix
1. Adopt the full contract after passing `borrowed_profile` in. Pass budget inputs explicitly. Move `validate_history` into `TransactionService`.
2. One balance-floor check, one `round_money`, and one `parse_id` in `core`.
3. One `open_profile_tasks()` for both entrypoints.
4. Split `profile_app` by area.

Each step is a branch of its own with tests unchanged.
