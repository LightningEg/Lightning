---
title: On a journal profile, retrying one add form can still save a second expense
type: bug
area: transactions
status: ready
created: 2026-10-23
by: Codex
skills: number-audit
app_version: 1.4.2
commit: a19c844
repo: app
---

## Report

Severity: medium. [Audit 4](../../reports/2026-10-23-backend-correctness/report.md) owns the original reproduction. [Audit 8](../../reports/2026-10-26-engine-audit/report.md) fixed it on ordinary profiles: the register, all-accounts register and add popups (PC and phone) carry a one-time `submission` token saved in `audit_log` in the same write, and a resent request returns its first save (`tests/test_engine_loose_ends.py`). Journal profiles skip that token, because their writes travel as journal commands and `lightning/sync/journal/` is claimed.

## Fix

Map the form's `submission` token to the journal command identity, so a retried HTTP request reuses its proposal instead of minting a new one. Test a repeated and a changed submission through `JournalServices`, on the home and on a replica.
