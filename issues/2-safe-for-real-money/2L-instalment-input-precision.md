---
title: A sub-cent purchase price creates a final instalment that cannot be paid
type: bug
area: planning
status: ready
created: 2026-10-23
by: Codex
skills: number-audit
app_version: 1.4.2
commit: a19c844
repo: app
---

## Report

Severity: medium. [Audit 4](../../reports/audit-4.md) owns the reproduction, expected behavior, source locations and scope for 2L. [Disposable probes](../../reports/audit-4/reproduce.py) and [captured results](../../reports/audit-4/results.txt) provide execution evidence.

## Fix

Reject price and fee inputs beyond their currency’s minor-unit precision before building an instalment schedule. Ensure every instalment can be posted and their exact sum equals the accepted purchase total. Include early-payment price/fee validation in the review.
