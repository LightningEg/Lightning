---
title: The shared posting API accepts a cash asset in the wrong account currency
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

Severity: medium. [Audit 4](../../reports/2026-10-23-backend-correctness/report.md) owns the reproduction, expected behavior, source locations and scope for 2I. [Disposable probes](../../reports/2026-10-23-backend-correctness/evidence/reproduce.py) and [captured results](../../reports/2026-10-23-backend-correctness/evidence/results.txt) provide execution evidence.

## Fix

Resolve account and asset metadata at the shared posting boundary; enforce matching currencies, real cash/non-cash identity and a rate of 1 for base-currency cash. Preserve foreign-currency conversion support. Test direct post/repost and existing builders.
