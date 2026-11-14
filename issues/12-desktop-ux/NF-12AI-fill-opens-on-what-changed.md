---
title: Fill opens on what changed and keeps the limits you set
type: feature
pillar: plan
size: M
model: opus
github: 635
status: ready
created: 2026-11-13
by: Claude
---

## Report
#626 findings 5-6 and stress test (2026-11-13). Fill's default source stops at the first selectable row, and unchanged last-month rows stay selectable, so an unchanged month opens on *Last month* while a new category's proposal sits under *Your average*. Average rows are preselected even where the user set a rule, so a deliberate 400 limit is replaced by a 550 average. A November-only 9,000 override is offered back in December as a "fixed" 9,000. `fit_fill` keeps whichever row comes first when room runs short, so row order decides.

## Fix
In `BudgetService.fill_proposal` and the Fill route: unchanged rows are not selectable and collapse into "N unchanged"; the default view is one list of real changes with each row's source (last month, average, schedule, goal); a row over an existing rule starts unticked with *Keep my limit / Use the average*; a past this-month-only override is labelled as such and never preselected. `fit_fill` stops at the shortfall and asks instead of keeping row order. PC and phone. Tests: the #626 scenarios (unchanged month opens on nothing to do; 400 limit not replaced by 550; override not offered as fixed; reversed row order gives the same result).
