---
title: Retrying one register submission creates a second expense
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

Severity: medium. [Audit 4](../../reports/audit-4.md) owns the reproduction, expected behavior, source locations and scope for 2J. [Disposable probes](../../reports/audit-4/reproduce.py) and [captured results](../../reports/audit-4/results.txt) provide execution evidence.

## Fix

Persist one per-submission operation ID, payload hash and result atomically with the write. Reuse it on retry and map it to journal command identity. Do not deduplicate by amount/date/counterparty: legitimate entries may be identical. Test repeated and concurrent requests and retries after a lost response.
