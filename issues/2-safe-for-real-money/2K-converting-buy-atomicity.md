---
title: A refused currency-converting buy leaves a new brokerage pocket
type: bug
area: investments
status: ready
created: 2026-10-23
by: Codex
github: 100
skills: number-audit
app_version: 1.4.2
commit: a19c844
repo: app
---

## Report

Severity: low. [Audit 4](../../reports/audit-4.md) owns the reproduction, expected behavior, source locations and scope for 2K. [Disposable probes](../../reports/audit-4/reproduce.py) and [captured results](../../reports/audit-4/results.txt) provide execution evidence.

## Fix

Start the outer transaction before route() can create a pocket. Inject failures during routing, conversion and purchase and assert unchanged account and posting rows. Keep successful converting buys covered.
