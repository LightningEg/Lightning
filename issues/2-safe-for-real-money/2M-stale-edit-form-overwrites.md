---
title: A stale transaction edit form can silently reverse a newer amount
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

Severity: high. [Audit 4](../../reports/audit-4.md) owns the button sequence, observed result, source locations and scope for 2M. [Workflow probes](../../reports/audit-4/workflow_probes.py) and [results](../../reports/audit-4/workflow-results.txt) reproduce it on temporary dummy ledgers.

## Fix

Include a revision/hash in each financial edit form, check it atomically when saving and preserve stale inputs for conflict review. Test note-only stale saves after amount, account and owner changes; include inline edit and journal form timing in the fix review.
