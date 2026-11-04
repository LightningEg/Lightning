---
title: Structure left - runtime routes and bank-import orchestration
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
2. **Done (2026-11-04): shared balance walk.** `core/balances.py` streams integer quantities for the owner, before/after cash and historical holding checks. Daily checks retain their daily netting; historical holdings retain `(date, transaction id, line number)` order. Messages, validation windows and treatment of existing deficits stay unchanged. No new global ordering policy was imposed; changing that policy would still require the owner’s decision. `tests/test_balance_walk.py` compares with the old SQL window, including same-day deficits, earliest ties, voids and seeded histories.

Done (2026-11-02, owner decision): **Budget no longer calls Planning through bootstrap callbacks.** Planning builds one
`PlanSchedule` per request (`c.schedules.view()`, `planning/schedule_view.py`); every budget call that depends on loans, bills,
recurring income or reserve goals takes it as `schedule=`; `forecaster.savings_rate` became the forecaster's `HealthService`;
`tests/test_architecture.py` pins that budgeting imports no planning and wires no callback. **The checked-month trigger has a code:**
migration 0069 recreates the five triggers of 0056 with `[LN-E0001]`, `database/connection.py` matches the code, the Arabic catalog
has the coded sentence, and `tests/test_checked_month_code.py` upgrades a schema-68 profile.

## Fix
One branch each, tests unchanged.

**Not posted to contributors (2026-10-31):** splitting `profile_app` touches the journal and device code that is claimed.


## Audit follow-up · 2026-11-03

The [code-quality audit](../../reports/2026-11-03-code-quality-and-smart-features/report.md) measures `profile_app` at 829 lines in commit 89848dc, rather than the older 746-line figure. After active runtime claims clear, retain the route-area extraction. Additional candidates within the same structural work: transaction service validation/search/submission collaborators (1,381-line facade), bank import parsing/proposals/posting (962-line module), and small typed reporting/page read models. Preserve public facades, transaction scopes, monetary invariants, replay and undo behavior; one extraction per change. These are refactoring opportunities, not new correctness findings.


## Transaction facade extraction · 2026-11-04

Complete: balance/certificate validation is in `transactions/balances.py`, read-only search/tags/capture suggestions in `transactions/search.py`, and exact submission fingerprints, duplicate delivery checks and revision hashing in `transactions/submissions.py`. The facade retains its signatures and policy constants; it still owns posting and save scopes. Audit rows, retry refusal messages and journal/Undo authority are unchanged. The shared balance walker does not buffer histories; the repository closes its streamed cursor. A 100,000-row dummy history agrees exactly with the former SQL window, with about 1.8 KB of Python allocations for the walk (SQLite allocations excluded); the local CPU sample was 407 ms versus 356 ms for the SQL window. This is a responsibility/consistency improvement, not a speed claim.

Still open: the unclaimed profile-route extraction, coordinated journal/device/recovery route separation after active claims clear, and the bank-import parsing/proposal/posting split. Keep one extraction per change and retain all financial behavior.

## Profile screens extracted · 2026-11-04

The profile lifecycle screens (list, new profile, unlock with password or fingerprint, recovery, password, question and recovery key) moved unchanged out of `profile_app` into `lightning/runtime/profile_screens.py`; the routes see the session, devices and gate through one `ProfileScreens` record, and `page`/`action` come back for the routes that stay. Restore, devices, borrowed-profile and Lock routes were not touched (they belong to the restore and journal claims). `runtime/app.py` is now about 750 lines. Existing profile, phone, restore and architecture tests pass unchanged; ruff and the import contracts pass.

Still open: restore, device and borrowed-profile routes after their claims clear, and the bank-import parsing/proposal/posting split.

## Bank import parsing · 2026-11-04

CSV decoding, numeric and date normalization, and row-level errors live in `bank_import_parsing.py`; `BankImportService` and the original helper imports remain available. The review proposals and duplicate/transfer/category suggestions now live in `bank_import_proposals.py`; the facade retains its preview interface. Posting orchestration stays open. Regression: `tests/test_bank_imports.py`, `tests/test_import_upload_limits.py`, `tests/test_architecture.py`.
