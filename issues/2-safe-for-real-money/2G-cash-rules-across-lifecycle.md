---
title: Cash balance rules can be bypassed by delete, restore, opening edits and conversion
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

Severity: high. [Audit 4](../../reports/audit-4.md) owns the reproduction, expected behavior, source locations and scope for 2G. [Disposable probes](../../reports/audit-4/reproduce.py) and [captured results](../../reports/audit-4/results.txt) provide execution evidence.

## Fix

Centralize cash and funding validation inside the write transaction for all lifecycle operations. Preserve the explicit import/system policy and harmless edits to existing deficits. Test deletion, restore, opening edits and unfunded conversions, including brokerage purchases.
