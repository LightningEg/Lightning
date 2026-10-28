---
title: The plan's fields blur bugs with owner asks, areas overlap, and reports miss their header lines
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

## 1K1 Owner decides the rule changes

- E1: keep `type` for what an item is; add `needs: owner` for who must act (7M, 7R, 7S are bugs filed as `owner`).
- E5: move app theme items 8J/8K/8L/8T out of Website, and 9L (plaintext legacy database) into milestone 2.
- E9: move reference reports such as users' main questions into `docs/`.

## 1K2 Make the generator check it

- E2: `severity` required for bugs and shown in INDEX.
- E3: a fixed `area` list in `tools/issues.py`.
- E4: warn when a `building` item has no claim in `NOW.md` (2B, 3H, 5G, 6A, 8J, 8L today).
- E7 done 2026-10-28: INDEX sorts `done:` lists.

## 1K3 Reports catalogue

- E8: test that each report has the `Reviewed commit` line (9 of 14 lack it), or relax the `evidence/` rule.
- E9: sorted by date 2026-10-28; Kind and Open follow-ups columns remain.
