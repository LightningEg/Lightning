---
title: Phone bulk Delete bypasses confirmation and does not show the selected count
type: bug
area: phone
status: ready
created: 2026-10-23
by: Codex
github: 102
skills: bug-hunt, number-audit
app_version: 1.4.2
commit: a19c844
repo: app
---

## Report

Severity: medium. [Audit 4](../../reports/audit-4.md) owns the button sequence, observed result, source locations and scope for 2O. [Workflow probes](../../reports/audit-4/workflow_probes.py) and [results](../../reports/audit-4/workflow-results.txt) reproduce it on temporary dummy ledgers.

## Fix

Handle the delete submitter, show the selected scope and preserve its formaction through confirmation. Test Cancel, confirm, repeated clicks, selection count, delete retry and Undo on the phone. Keep category-change behavior working.
