---
title: The payday proposal's lines do not add up to the cash they share out, and "Everyday spending" there is not the figure of that name
type: bug
look: technical
severity: medium
pillar: plan
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: number-audit
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r36 F5 ([report](../11-phone-ux/r36-figures-one-owner/report.md), [page text](../11-phone-ux/r36-figures-one-owner/evidence/sample-pages.json), key `phone:/payday`; r27 J4 called it ambiguous). Mohab's sample year, 2026-10-21, "Your payday proposal" on PC and phone:

- Bills protected 15,740 · Everyday spending 35,018 · Emergency and goals 98,183 · Left unassigned 0
- "Cash available to assign: 117,461 → after you confirm 0"

35,018 + 98,183 = 133,201, which is 15,740 more than 117,461. In `lightning/planning/funding.py` (lines 86-89) a category's suggested amount may draw on `pool + protected`, so the cash protected for bills is inside the spending line and is also shown as its own line. On the demo household (no bill due) the lines add up: 0 + 6,598 + 60,420 = 67,018.

The line called "Everyday spending" is what the plan would be given (here the month's Left in plan, 35,018). The registry's Everyday spending is what was spent so far this month less paid bills (3,410 on the same day).

## Fix

The four lines are disjoint and sum to the cash they start from: either Cash available to assign is stated before bills and Bills protected is one of its parts, or the spending line is shown net of the protected bills. The proposal's totals are returned by `CashFundingService.preview` with that identity, and the second line is renamed for what it is (for example "To your plan"), in English and Arabic.

Test: for the demo household and Mohab's year, `bills + spending + reserves + unassigned == available_before` under the chosen definition, and the template renders no registry label for a different figure. Then Mohab's payday step.
