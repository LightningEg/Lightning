---
title: Cover all backend modules with explicit dependency and wiring contracts
type: tech
pillar: build
size: M
status: ready
post: no
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

**Not posted to contributors (2026-10-31):** it is architecture work across the sync, financial and runtime layers, which overlaps the claimed journal code; it needs splitting by layer first.

## Follow-up (2026-11-04)

The top-level layer inventory is enforced. Sync now assigns every Python module and package initializer to a protocol, financial adapter or runtime policy; `tools/backend_policy.py` checks assignments and direct imports, including a documented codec exception. Dynamic imports are outside this static check. Regressions: `tests/test_architecture.py`.

Investment reevaluation and forecast deposit and receipt providers are now required and checked at construction; the composition root supplies them before either service is usable. Direct financial-adapter imports of runtime modules are prohibited except the existing finance-to-store dependency. Budget receives `ScheduleView` explicitly under 9K.

Still open: audit other late composition wiring, including undo setup, and assess remaining runtime boundaries. Package-registry imports and dynamic imports are outside the adapter-to-runtime static check.
