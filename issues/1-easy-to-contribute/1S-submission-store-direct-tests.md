---
title: Direct tests for SubmissionStore (a form saved twice saves once)
type: tech
pillar: build
size: S
status: ready
created: 2026-11-05
by: Claude Sonnet 5.5
app_version: 1.5.4
repo: app
---

## Report
Release 1.5.4 fixed forms sent twice, but `SubmissionStore` in `lightning/transactions/submissions.py` has no direct test; it is covered only through routes.

## Done when
`tests/test_submission_store.py` checks: the same token and payload returns the first transaction; the same token with other values raises "This form was already saved"; a voided transaction raises; `form_seen` and `remember_form` behave the same for a form that saved something other than one transaction; no token means nothing is remembered. It passes under `python -m pytest`.

Where to look: `lightning/transactions/submissions.py`.
Read first: any test that builds a `Database` and an `AuditLog`, for the fixture.
