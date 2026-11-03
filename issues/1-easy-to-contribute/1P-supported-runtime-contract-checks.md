---
title: Check the minimum supported Python and asynchronous UI contracts
type: tech
pillar: build
size: M
status: new
post: no
created: 2026-11-03
by: Codex
app_version: 1.5.4
commit: 89848dc0e4ce35bb18f72e861c7c620d8052fae4
repo: app
---

## Report

[Code audit F4](../../reports/2026-11-03-code-quality-and-smart-features/report.md). `pyproject.toml` supports Python >=3.11; the PR test job selects 3.13. Existing phone-search tests exercise server HTML but not delayed response bodies. This is a coverage gap, not proof that 3.11 is broken.

## Fix

Add a small minimum-supported-Python contract job for pure money/date/import logic with compatible dependency inputs, keeping the full suite on the existing interpreter. Add deterministic asynchronous tests for search response ordering and cancellation (BT-3AP owns its implementation). Document which package/device checks run manually and which PR changes require them. Avoid a full expensive OS/interpreter matrix. Acceptance: a minimum-runtime-incompatible change and a stale search body each fail the appropriate gate.

Not posted: changes CI cost and dependency/packaging contracts; coordinate with IT-1H.
