---
title: Five more money forms save twice when the same form is sent again - investment entry, gold trade, ownership change, money held for others, instalment purchase
type: bug
look: technical
severity: low
pillar: capture
size: M
status: ready
created: 2026-10-29
by: Claude
skills: bug-hunt, number-audit
app_version: 1.5.1
commit: 045ccd4
repo: app
---

## Report

Found by the [use-case audit](../../reports/2026-10-29-use-case-audit/report.md) (F4). On ordinary profiles the register, add popups, Quick Add, conversion, certificate purchase and gam'eya instalment forms carry a one-time `submission` token (2J; the last three since this audit), so a resent request returns its first save. These still post again when the same form is sent twice: the investment entry form (`/investments/new`, `/accounts/{id}/investment-entry`), a gold item buy or sell (`/accounts/{id}/items/{asset}/trade`), an ownership change (`/accounts/{id}/ownership/new`), money held for others (`/money-from-others`) and Bought in instalments (`/plan/purchases/new`). The busy button in `app.js` stops an ordinary double click; a resent request (a retry, a reload that re-posts, two quick Enters on a form with no default button) is not stopped. Severity low.

## Fix

Same pattern as the conversion route (`lightning/ui/routes/accounts.py`, `save_conversion`): a hidden `submission` from `new_submission()` in each form, and inside one `c.db.transaction()` call `c.transactions.submitted(...)` first and `remember_submission(...)` after the save. Skip it on journal profiles (2J). Extend `tests/test_engine_loose_ends.py::test_a_resent_money_form_saves_once` with each form.
