---
title: Budget's "One-off" and "this month only" say what they really do, with scope and an undo
type: polish
look: visual
pillar: plan
size: M
model: sonnet
github: 634
status: ready
created: 2026-11-13
by: Claude
---

## Report
#626 finding 1-3 (2026-11-13). Budget › Edit plan › Not tracked offers **One-off** per category; it saves a lasting category exclusion (`budgeting/service.py` `one_off_ids`, children included), not "this purchase was unusual". A budget rule's one-off flag means something else: a limit for this month only. Both say "one-off"; neither shows its scope or where the spending still shows (cash flow, analysis).

## Fix
Wording and UI only, no financial change. Rename the category action to *Leave out of budget estimates* and show "and its N subcategories" when it has children, with *Put back* beside each excluded row. Name the rule flag *Limit for this month only*. One line under the excluded list: the spending still counts in Cash flow and Spending. PC and phone (`phone/budget_flexible.html`), English and Arabic. Test: the labels, the scope count and *Put back* round-trip; `test_mohab_year.py` unchanged.
