---
title: Move in from Wallet, Money Manager and Masareef exports
type: feature
pillar: capture
size: L
model: opus
status: new
created: 2026-10-19
by: Claude
---

## Report

Idea from Say reviews: read the exports of Wallet, Money Manager and Masareef, carry their categories, accounts and
dates through a preset per app in the CSV review, and add a move-in guide screen.

## Owner decision · 2026-11-04

The owner excluded NF-7C app migration from the Section 7 implementation request (`NOW.md` Messages, Owner
2026-11-04; `ai/PROJECT_OVERVIEW.md`, "Section 7 owner decisions (2026-11-04): NF-7C migration is excluded").
Leave this item unbuilt.

2026-11-08: the exclusion covers the whole item: the three steps (7C1 read each app's export, 7C2 a mapping preset
per app, 7C3 a move-in guide) are all app migration, so none is left to build; their codes are retired, not reused.
What a person needs to move in from another app's export is already built generically by IT-7Z
(f387e5d3, `tests/test_import_other_app_exports.py`: the other app's category group, its balance rows waiting as
Skip, and each of its category names set once), plus the saved column mapping per account.

## 7C4 Close this item or keep it parked · owner
Asked in the question dialog. (a) **(Recommended)** Close NF-7C: the owner excluded it, and IT-7Z already imports
another app's CSV export with its categories; delete this file and add 7C to the folder's `done:` as excluded.
(b) Keep it parked unbuilt for a later release (it stays in the plan with no steps to take).
(c) Bring back only the move-in guide (one help screen saying how to export a CSV from each app, no per-app parser);
then a step is written for it.
