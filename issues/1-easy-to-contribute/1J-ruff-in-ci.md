---
title: Unused imports and variables keep coming back - ruff is not run in CI
type: tech
area: tools
status: ready
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

`ruff check lightning tools --select F401,F841,F811,B023,B018` finds 58 findings: 32 unused imports, 16 unused variables, one name defined twice in `sync/journal/cloud.py:127,150`. The B023/B018 hits checked are false positives (`runtime/devices.py:165` reads the record on purpose). Ruff is not in CI or `pyproject.toml`. Audit 9 C1: `../../reports/2026-10-28-loose-ends-and-linking/report.md`.

## Fix

Add a `[tool.ruff]` section selecting `F401,F841,F811`, fix or `noqa` with a reason each hit, and run `ruff check` in the Linux workflow. Journal files wait for the journal claim in `NOW.md`.
