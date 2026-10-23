---
title: A refused mass edit loses the selected rows and the typed correction
type: bug
area: transactions
status: ready
created: 2026-10-23
by: Codex
skills: bug-hunt, number-audit
app_version: 1.4.2
commit: a19c844
repo: app
---

## Report

Severity: medium. [Audit 4](../../reports/audit-4.md) owns the button sequence, observed result, source locations and scope for 3AE. [Workflow probes](../../reports/audit-4/workflow_probes.py) and [results](../../reports/audit-4/workflow-results.txt) reproduce it on temporary dummy ledgers.

## Fix

Retain the selected IDs and changed fields until success; restore them after a refused bulk save. Show which rows blocked the action so the person can adjust the scope or unlock history. Cover checked history and other validation failures in a real browser.
