---
title: Investigate existing Linux browser and packaging test failures
type: tech
pillar: build
size: M
model: sonnet
status: ready
created: 2026-11-08
by: Codex
repo: app
---

## Report

PR #385's full local Python 3.12 run exposed failures outside its schedule-test changes. A separate checkout of unchanged main `82a915fb` reproduced five of them:

- `tests/test_feedback_fixes_browser.py::test_register_selection_survives_edit_without_submitting`: the transfer has one selection control, while the test expects two. Check the desktop ledger changes in #386 before changing the assertion.
- `tests/test_journal_pairing_native_browser.py::test_native_discovery_number_choices_and_password`: all three viewport cases time out waiting for the "Approve this device" button. Coordinate with the journal claim in `NOW.md` before touching implementation files.
- `tests/test_profile_packaging.py::test_notices_follow_what_pyinstaller_actually_bundled`: the installed-distribution lookup omits Jinja2 in this workspace's shared Python environment. Determine whether isolated, locked environments reproduce it before changing the packager.

`tests/test_brand_audit.py::test_counterparty_controls_do_not_overlap_and_alias_saves_with_enter` failed `alias_saved` during the full run but passed on the unchanged-main retry; investigate timing before calling it a product regression.

Reproduce with `python -m pytest -q -n 3 --dist loadfile tests/test_feedback_fixes_browser.py::test_register_selection_survives_edit_without_submitting tests/test_journal_pairing_native_browser.py tests/test_profile_packaging.py::test_notices_follow_what_pyinstaller_actually_bundled`. Browser tests need the project's browser prerequisites. FastAPI TestClient hangs under this workspace's execution sandbox; an isolated minimal probe worked outside it.

Seven additional Excel failures disappeared after installing the already-declared `defusedxml==0.7.1`; those were environment setup failures, not app changes. PR #385's five schedule cases pass.

### Follow-up · 2026-11-08 · PR #399 review

With isolated Python 3.13.5 and the hashed Linux probe and browser dependencies, unchanged main `3a948524` also fails `tests/test_sms_imports.py::test_cash_withdrawal_is_a_transfer_and_salary_has_its_own_choice`: the generated salary CSV reaches `bank_imports.preview()` and raises `Could not read this CSV: Could not determine delimiter`. The same failure occurs in PR #399's full run. Check the interpreter/CSV-sniffer behavior before treating it as a regression from unrelated UI work. Reproduce with `python -m pytest tests/test_sms_imports.py::test_cash_withdrawal_is_a_transfer_and_salary_has_its_own_choice -q`.

The investment-link styling, register-selection assertion and all three native-pairing cases also reproduce on that unchanged main. The earlier packaging-notice failure does not recur in the isolated, locked environment.

## Fix

Reproduce with locked dependencies and browser prerequisites. Repair stale assertions or environment discovery where appropriate, fix any confirmed implementation defect with its owner, and stabilize the counterparty browser check. Keep the existing assertions meaningful; do not skip or disable tests to make checks pass.

### Follow-up · 2026-11-08 · PR #439 review

The bounded delimiter fallback in #439 fixes the quoted multiline salary CSV failure above: `tests/test_sms_imports.py` now passes together with the statement/import acceptance regressions on the isolated Python 3.13.5 environment. The isolated-environment packaging result remains good. The full brand audit still reproduces the investment-link styling failure; it is independent of the import diff and remains to investigate here.
