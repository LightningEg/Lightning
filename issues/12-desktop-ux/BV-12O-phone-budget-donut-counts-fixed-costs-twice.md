---
title: Phone Budget: Where the month went counts fixed costs twice (33,851 spent where 19,001 was)
type: bug
look: visual
severity: high
pillar: plan
size: S
model: sonnet
status: ready
created: 2026-11-09
by: Claude
skills: bug-hunt, guideline-audit
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r32](r32-budget-and-cash-planning/report.md) N1. Evidence: [phone Budget](r32-budget-and-cash-planning/evidence/phone-budget.png). The donut says 33,851 Spent with slices
Fixed costs 14,850, Housing & Rent 12,000, Food & Groceries 3,251, Loan payments 2,500, Other 1,250. The PC says Spent
19,001. Fixed costs paid (rent 12,000 + loan 2,500 + Vodafone 350 = 14,850) are already inside their categories:
`lightning/ui/phone/screens/budget.py` `spend_donut(rows, paid)` adds every category's spending and then the fixed
costs paid again.

## Fix
Build the slices from the flexible rows plus one Fixed costs slice, with fixed payments taken out of their categories
(or categories only, no Fixed slice): the total must equal the month's spending. Test: on the sample month the donut's
total is 19,001 and equals the PC's Spent.
