---
title: Editing account or owner can leave the previous account negative or owner with negative shares
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

Severity: high. [Audit 4](../../reports/audit-4.md) owns the reproduction, expected behavior, source locations and scope for 2H. [Disposable probes](../../reports/audit-4/reproduce.py) and [captured results](../../reports/audit-4/results.txt) provide execution evidence.

## Fix

Validate the union of removed and proposed account/asset/owner keys over their dated history. Test moving funding income, changing a transfer destination and reassigning a purchase that funded another owner’s sale.
