---
title: Cover all backend modules with explicit dependency and wiring contracts
type: tech
area: tools
status: ready
created: 2026-10-23
by: Codex
skills: number-audit
app_version: 1.4.2
commit: a19c844
repo: app
---

## Report

[Audit 4](../../reports/2026-10-23-backend-correctness/report.md) owns the reproduction, expected behavior, source locations and scope for 1G. [Disposable probes](../../reports/2026-10-23-backend-correctness/evidence/reproduce.py) and [captured results](../../reports/2026-10-23-backend-correctness/evidence/results.txt) provide execution evidence.

## Fix

Assign every production module to an explicit dependency policy or documented exemption and enforce coverage. Separate sync protocol, financial adapters and runtime boundaries. Make required wiring explicit through protocols or a validated composition phase.
