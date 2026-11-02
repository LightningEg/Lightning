---
title: Structure left - a 746-line profile_app and three balance-floor checks
type: tech
pillar: build
size: M
status: ready
post: no
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
2. **Three balance-floor checks**: `_validate_owner_balances`, `_refuse_cash_below_zero`, `lowest_running_quantity`. One shared
   running-balance helper, with each caller's refusal message kept. Careful: merging them could change the order in which
   same-day entries are checked, so it needs a decision on that order first.

Done (2026-11-02, owner decision): **Budget no longer calls Planning through bootstrap callbacks.** Planning builds one
`PlanSchedule` per request (`c.schedules.view()`, `planning/schedule_view.py`); every budget call that depends on loans, bills,
recurring income or reserve goals takes it as `schedule=`; `forecaster.savings_rate` became the forecaster's `HealthService`;
`tests/test_architecture.py` pins that budgeting imports no planning and wires no callback. **The checked-month trigger has a code:**
migration 0069 recreates the five triggers of 0056 with `[LN-E0001]`, `database/connection.py` matches the code, the Arabic catalog
has the coded sentence, and `tests/test_checked_month_code.py` upgrades a schema-68 profile.

## Fix
One branch each, tests unchanged.

**Not posted to contributors (2026-10-31):** splitting `profile_app` touches the journal and device code that is claimed.
