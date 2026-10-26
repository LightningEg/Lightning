---
title: Structure left - a 746-line profile_app, budgeting calls planning through bootstrap, three balance-floor checks
type: tech
area: architecture
status: ready
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 5](../../reports/2026-10-21-backend-streamlining/report.md) §4. Done (2026-10-22): every module has a layer in the import contract (a test keeps
it so; `sync.transport.join_home` takes `borrowed_profile` instead of importing upward); one `core/refs.parse_row_id` replaces four
id checks; Undo's ledger check is `transactions/history_check.validate_replay`, not a bootstrap closure; `open_profile_tasks` is one
list for both entrypoints (month-end checkpoints post on unlock, failures are logged); `MoneyFromOthersService` gets its
`CounterpartyService` from bootstrap; the one-off budget lookup catches only `NotFoundError`; Architecture › Persistence says why money has two roundings. Left:

1. **`runtime/app.py:profile_app`** is one 746-line function of nested routes; split it by area (profiles, devices, restore).
   The journal and device code it wires belong to claimed work (4A, 2A): split after those claims clear.
2. **Budgeting calls planning through bootstrap callbacks** (`budgets.scheduled_*`, `reserve_goal_needs`, `savings_rate`), a
   higher layer the linter cannot see. Pass those inputs into the budget calls instead.
3. **Three balance-floor checks**: `_validate_owner_balances`, `_refuse_cash_below_zero`, `lowest_running_quantity`. One shared
   running-balance helper, with each caller's refusal message kept.
4. `database/connection.py` matches a trigger's message text to turn it into a `ValidationError`; give the trigger a code.

## Fix
One branch each, tests unchanged.
