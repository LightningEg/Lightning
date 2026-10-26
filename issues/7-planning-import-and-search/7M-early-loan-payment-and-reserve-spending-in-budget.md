---
title: Paying a loan early empties the everyday budget, and an expense paid from a reserve still counts as overspending
type: owner
area: planning
status: new
created: 2026-10-20
by: Claude
skills: number-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§1, §2). Both are documented behaviour, but both make Budget give the wrong advice in a demo.

1. **Early loan payment.** Demo: pay the car loan early, 5,000 principal + 100 fee. Net worth −100 and loans −5,000 are right, but Money out +5,100,
   savings rate 58.4% → 47.5%, Left in plan 5,559 → 459, everyday 5,079 → 0, while Safe to spend falls by only 21. `planning/forecast.py:174` pools the
   overspend in the loan category with everyday money (`docs/ARCHITECTURE.md:212`).
2. **Expense paid from a reserve.** After linking a 6,500 repair to the emergency fund (20,000 → 13,500), Budget still shows Transportation 3,551 over
   and suggests moving money from Entertainment.

## Fix
Owner decisions, given "Reserves are not budgets": (1) should principal paid early count as Money out and against everyday money, or as saving?
(2) should an expense covered by a reserve count against its budget category? Then `budgeting/service.py` actuals and `CashForecaster.everyday`.
