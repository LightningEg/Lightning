---
title: Compare scenarios agrees with itself, and a checked purchase can be planned
type: bug
look: visual
severity: medium
pillar: plan
size: L
model: opus
status: new
created: 2026-11-14
by: Claude
github: 671
---

## Report
[r37](r37-cash-planning-workflow/report.md) W3, W7, L3, M2, M3. Buy 60,000 on 20 Nov in Compare scenarios: the lead is −8,580 and the card beside it says "First shortfall: No shortfall"; the headline says only "lowers your lowest point ahead by 60,000". Salary 20 days late: "leaves your lowest point ahead where it is" (month-end only). *Can I afford this?* ignores its date unless an account is chosen. Neither answer can be kept: there is no way to put the purchase in the plan except *Add recurring item* with Repeats: Once. Reproduce: `evidence/flows/d.js`, `a.js`.

## Fix
## 7AW1 One answer on the scenarios page · M · opus
The lead, the headline and *What changes* use one measure; below zero the headline says "You would be N short in <month>". A late income shows the lowest day, not only month ends. Done when: `tests/test_scenarios.py` covers a purchase below zero and a salary late inside one month, on the PC and the phone (the phone drops "Lowest scheduled cash").

## 7AW2 Plan this purchase · M · sonnet
*Can I afford this?* and a scenario result offer "Plan this purchase": the one-off item form, prefilled. The afford date counts with or without an account, and a past date is refused. Done when: a test follows the link and finds the purchase in the forecast month; the phone gets *Can I afford this?* (M1).
