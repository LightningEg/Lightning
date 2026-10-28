---
title: Ruff skips the journal files until their claim merges
type: tech
area: tools
status: ready
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

Audit 9 C1 (`../../reports/2026-10-28-loose-ends-and-linking/report.md`) found unused imports and variables. Done 2026-10-28
(`claude/audit-9-quick-fixes`, `claude/plan-checks-and-lint`): every hit outside the journal files, `[tool.ruff]` in
`pyproject.toml` (F401, F811, F841) and `ruff check lightning tools` in `.github/workflows/pr-checks.yml`.
Left: the journal files, excluded in `pyproject.toml` while `claude/sync-errors-and-journal-tidy` holds them.

## Fix

Once that branch merges, delete the `extend-exclude` list in `pyproject.toml` and fix what `ruff check lightning tools` finds.
