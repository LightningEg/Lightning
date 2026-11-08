---
title: Structure left - restore, device and borrowing routes out of profile_app
type: tech
pillar: build
size: M
model: opus
status: ready
post: no
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 5](../4-edit-journal-and-devices/r3-backend-streamlining/report.md) §4. Done (2026-10-22): every module has a layer in the import contract (a test keeps
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

The [code-quality audit](r22-code-quality-and-smart-features/report.md) measures `profile_app` at 829 lines in commit 89848dc, rather than the older 746-line figure. After active runtime claims clear, retain the route-area extraction. Additional candidates within the same structural work: transaction service validation/search/submission collaborators (1,381-line facade), bank import parsing/proposals/posting (962-line module), and small typed reporting/page read models. Preserve public facades, transaction scopes, monetary invariants, replay and undo behavior; one extraction per change. These are refactoring opportunities, not new correctness findings.


## Transaction facade extraction · 2026-11-04

Complete: balance/certificate validation is in `transactions/balances.py`, read-only search/tags/capture suggestions in `transactions/search.py`, and exact submission fingerprints, duplicate delivery checks and revision hashing in `transactions/submissions.py`. The facade retains its signatures and policy constants; it still owns posting and save scopes. Audit rows, retry refusal messages and journal/Undo authority are unchanged. The shared balance walker does not buffer histories; the repository closes its streamed cursor. A 100,000-row dummy history agrees exactly with the former SQL window, with about 1.8 KB of Python allocations for the walk (SQLite allocations excluded); the local CPU sample was 407 ms versus 356 ms for the SQL window. This is a responsibility/consistency improvement, not a speed claim.

The profile screens and bank-import boundaries are completed below. Journal/device/recovery route separation stays open after active claims clear.

## Profile screens extracted · 2026-11-04

The profile lifecycle screens (list, new profile, unlock with password or fingerprint, recovery, password, question and recovery key) moved unchanged out of `profile_app` into `lightning/runtime/profile_screens.py`; the routes see the session, devices and gate through one `ProfileScreens` record, and `page`/`action` come back for the routes that stay. Restore, devices, borrowed-profile and Lock routes were not touched (they belong to the restore and journal claims). `runtime/app.py` is now about 750 lines. Existing profile, phone, restore and architecture tests pass unchanged; ruff and the import contracts pass.

Still open: restore, device and borrowed-profile routes after their claims clear.

## Bank import parsing · 2026-11-04

CSV decoding, numeric and date normalization, and row-level errors live in `bank_import_parsing.py`; `BankImportService` and the original helper imports remain available. The review proposals and duplicate/transfer/category suggestions now live in `bank_import_proposals.py`; the facade retains its preview interface. Posting and linking one reviewed row now live in `bank_import_posting.py`; the facade still owns confirmation ordering, transaction and rollback scopes. Regression: `tests/test_bank_imports.py`, `tests/test_import_upload_limits.py`, `tests/test_architecture.py`.

The upstream `bank_import_rows.py` readers remain authoritative and the journal uses them; normalization delegates to those same readers. Remaining: claimed restore/device routes. Undo validators are now passed before attachment in this branch.

## Checked · 2026-11-08

On main: profile lifecycle screens live in `lightning/runtime/profile_screens.py` (#300); bank-import parsing, proposals and posting live in `lightning/bank_import_parsing.py`, `bank_import_proposals.py` and `bank_import_posting.py` (merged), so the bank-import half of the title is done. The balance walk (2) and the transaction facade are done. `lightning/runtime/app.py` is 764 lines; `profile_app` runs from line 191 to the end, and its routes still hold restore (`/profiles/restore`, `/profiles/restore/resume`), Lock (`/profiles/lock`, which calls `hand_back`), the phone's device routes (`/profiles/devices*`) and the PC's borrowing routes (`/profiles/connect`, `/profiles/borrowed`, `/profiles/receive`, `/profiles/move`, `/profiles/hand-back` and `/sync/hand-back`). The 2A restore claim is gone from `NOW.md`; the one claim left covers `lightning/runtime/journal*`, which these steps do not touch (the journal routers are only included from `profile_app`).

## How to work on this item

Each step below is one pull request that **moves code unchanged**: same routes, same messages, same status codes, no test edited. Copy the pattern of `lightning/runtime/profile_screens.py` (a dataclass of what the routes need, a `register(app, screens)` function) and read only the lines of `lightning/runtime/app.py` the step names. Run `python -m pytest tests/test_profile_app.py tests/test_architecture.py tests/test_devices_app.py -q` plus the step's own tests, and `ruff check lightning tools`; delete the step's heading in the same commit.

## 9K1 Restore routes out of profile_app · S · sonnet
Files: `lightning/runtime/app.py` (the four routes `restore_page`, `restore`, `resume_restore_page`, `resume_restore`, about lines 365-425); new `lightning/runtime/restore_screens.py`; `pyproject.toml` `[tool.importlinter]` layers only if `tests/test_architecture.py::test_every_production_module_has_a_layer` asks for the new module.
Do: move the four routes, word for word, into `register(app, session, devices, page)` in `restore_screens.py` (they use only `session`, `devices.blocks_restore` and `page`), and call it from `profile_app` right after `page, action = screens.page, screens.action`. Module docstring: what moved and why (IT-9K). Do not touch `/profiles/lock`.
Done when: `python -m pytest tests/test_profile_app.py tests/test_sync_review.py tests/test_architecture.py -q` (the tests that post to `/profiles/restore`) passes unchanged, and `grep -n "profiles/restore" lightning/runtime/app.py` is empty.

## 9K2 The phone's device routes out of profile_app · M · opus
Needs 9K1 merged first.
Files: `lightning/runtime/app.py` (`device_page`, `phone_device_page`, `pc_device_page`, `home_only` and the routes `/profiles/devices`, `/profiles/devices/pair`, `/profiles/devices/keep-home`, `/profiles/devices/stop-pairing`, `/profiles/devices/revoke`, `/profiles/devices/take-back`, about lines 436-562); new `lightning/runtime/device_screens.py`.
Do: move them unchanged behind a `DeviceScreens` dataclass holding `session`, `devices`, `gate`, `page` and `app` (two routes set `app.state.container`; pass `app` rather than reaching for a global). Opus because pairing, revocation and take-back move a real ledger between devices: check by reading that no closure variable is captured differently after the move (each `nonlocal` or late-bound name), and that `device_page`'s redirect to `/journal/devices` when `session.journal` is set is kept.
Done when: `python -m pytest tests/test_devices_app.py tests/test_two_devices.py tests/test_device_roundtrip.py tests/test_pairing_entrypoints.py tests/test_profile_app.py tests/test_architecture.py -q` passes unchanged and `grep -n "profiles/devices" lightning/runtime/app.py` is empty.

## 9K3 The PC's borrowing routes and Lock out of profile_app · M · opus
Needs 9K2 merged first.
Files: `lightning/runtime/app.py` (`/profiles/lock`, `/profiles/connect`, `/profiles/borrowed`, `/profiles/receive`, `/profiles/move`, `/profiles/hand-back` and `/sync/hand-back`, from about line 427 and from about line 563 to the `secured = Guard(...)` line); new `lightning/runtime/borrow_screens.py`.
Do: move them unchanged; `lock` calls `hand_back`, so both move together. Keep `open_profile_id`, `kept` and `session.borrowed_home` handling exactly as they are (pass `open_profile_id` and `kept` in the dataclass). Opus for the same reason as 9K2 (a borrowed ledger and its hand-back). After this step `profile_app` should only build the app, wire the session, gate and routers, and return the `Guard`; this is the item's last step, so finish the item in the same commit: delete this file and add `9K` to `done:` in `issues/9-later/README.md` (AGENTS.md §3).
Done when: `python -m pytest tests/test_two_devices.py tests/test_devices_app.py tests/test_profile_app.py tests/test_profile_session.py tests/test_architecture.py -q` passes unchanged, and `grep -c "@app\." lightning/runtime/app.py` counts only the routes that stay (health, checking, read-only, `__activity`).
