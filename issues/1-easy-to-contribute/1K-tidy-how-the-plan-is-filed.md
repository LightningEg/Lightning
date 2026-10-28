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

## 1K1 Owner decisions (2026-10-28)

- E1: keep owner-blocked bugs as owner tasks (OW); no `needs:` field.
- E5: done - app theme items moved to milestone 10 Looks and store (8J→10A, 8K→10B, 8L→10C, 8T→10D), 9L→2AA, 6E→3AI.
- E9: users' main questions stays in reports as Kind: reference.

## 1K2 Make the generator check it

- E2: `severity` required for bugs and shown in INDEX.
- E3: a fixed `area` list in `tools/issues.py`.
- E4: warn when a `building` item has no claim in `NOW.md` (2B, 3H, 5G, 6A, 8J, 8L today).
- E7 done 2026-10-28: INDEX sorts `done:` lists.

## 1K3 Reports catalogue

- E8: test that each report has the `Reviewed commit` line (9 of 14 lack it), or relax the `evidence/` rule.
- E9: sorted by date 2026-10-28; Kind and Open follow-ups columns remain.
