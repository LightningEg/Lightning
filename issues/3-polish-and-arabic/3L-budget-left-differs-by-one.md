---
title: Budget "left" reads 37 in the meters and +38 in the detail table
type: bug
area: budget
status: new
created: 2026-10-19
by: Claude Sonnet 5.5
skills: number-audit
app_version: 1.3.0
commit: a926b57
repo: app
---

## Report
Budget, demo data (`--demo`, 2026-10): Eating Out planned 671, spent 633.50. "Spent of plan" says 37 left; the budget detail table says +38. The meter uses `_gap` (`lightning/ui/charts.py:23`), which subtracts the two rounded figures (671 − 634); the table rounds the true 37.50 half up (A: whole EGP rounds half up everywhere).
Pick one rule for every "left" on the page (the true gap rounded half up reads right beside the true figures; the rounded subtraction reads right beside the rounded figures) and test it with a half-cent case. Severity: low.
