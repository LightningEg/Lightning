---
title: Fill this month from your average of the last three months
type: feature
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
[r32](r32-budget-and-cash-planning/report.md) F1 (owner chose it, 2026-11-09). *Fill this month* offers Last month, Schedule and Goal. With no
limits last month it has nothing to offer, and last month's limit says nothing about what was actually spent.

## Fix
A fourth source, *Your average*: each category's spending averaged over the last three full months (one-off categories
left out, as the budget already does), rounded to a tidy figure, shown beside the current limit with the rows ticked
by default. `BudgetService.fill_proposal` gets the source; nothing is saved until applied. Tests: proposal values on
the sample household; a category with one month of history uses that month.
