---
title: Expense Save can return an error after the money has already posted
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

Severity: high. [Audit 4](../../reports/audit-4.md) owns the button sequence, observed result, source locations and scope for 2N. [Workflow probes](../../reports/audit-4/workflow_probes.py) and [results](../../reports/audit-4/workflow-results.txt) reproduce it on temporary dummy ledgers.

## Fix

Make the workflow commit boundary explicit and distinguish a successful posting from failed optional feedback. Reproduce with an unrelated foreign bill lacking FX; assert the response and persisted state agree, including a repeated submit. Coordinate with 2J idempotency.
