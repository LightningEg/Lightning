---
title: The import review says what it will do: honest duplicate notes, less repetition, a true summary
type: polish
pillar: capture
size: M
status: ready
created: 2026-11-05
by: Claude Opus 5.5
---

## Report
From [the report](../../reports/2026-11-05-import-scenarios/report.md) (F14-F18):
- A one-row group shows its name, amount and state twice (group line, then the row): "a line that repeats its label" (A16).
  A one-row group can be the row itself.
- "Transfer across currencies" is folded under **every** row of an EGP statement when no other-currency account exists.
- The look-alike note says "Same date and amount as a row you already have" when the dates differ (salary on the 4th
  against an entry on the 1st), and never names the entry it means.
- A row that will link to an entry you typed is still labelled "Possible duplicate" in red-ish wording; it is the good
  outcome ("Already in your books").
- After posting, "Import complete: 0 posted, 44 linked, 0 skipped, 2 duplicates" does not say what the 2 were or their
  total; the person has no way to see what was left out.

## Fix
- Show the group line only for two or more rows.
- Show the currency fold only when the person has an account in another currency.
- Note: "Matches <name> on <date>" with the real date; state word "Already recorded" for a default link.
- The summary lists what was skipped as a duplicate with its total and a link to reopen those rows.
