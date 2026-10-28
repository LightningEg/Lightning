---
title: The plan's fields blur bugs with owner asks, and some items sit in the wrong milestone
type: tech
area: docs
status: new
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

Audit 9 part E (`../../reports/2026-10-28-loose-ends-and-linking/report.md`) checked every item's front matter and every report.
Done 2026-10-28 (`claude/plan-checks-and-lint`): bugs carry `severity`, areas are a fixed list (`tools/issues.py` `AREAS`),
`--check` warns about a `building` item with no claim, and the reports catalogue has Kind and Open follow-ups columns, with
`Date:` and `Reviewed commit:` header lines tested (`tests/test_issues.py`, `tests/test_docs_structure.py`).

## 1K1 Owner decides the rule changes

- E1: keep `type` for what an item is; add `needs: owner` for who must act (7M, 7R, 7S are bugs filed as `owner`).
- E5: move app theme items 8J/8K/8L/8T out of Website, and 9L (plaintext legacy database) into milestone 2.
- E9: move reference reports such as users' main questions into `docs/`.
