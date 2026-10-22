---
title: Routes still compute figures, some that no screen shows
type: tech
area: ui
status: ready
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 4](../../reports/audit-4.md) §4. This breaks the rule "Routes never compute figures" (Architecture › Three layers), and [7N](../7-planning-import-and-search/7N-bills-before-payday-two-formulas.md) is the wrong figure it has already caused.

- **`dashboard`** (`ui/routes/dashboard.py:93`) builds eight figures no PC or phone template reads: `account_contributions`, `expense_groups` (about 40 lines), `investment_holdings`, `investment_flow`, `investment_share`, `range_label`, `change_label`, `change_reason`.
  - `investment_share` divides money added by money in; the registry's investing rate divides by net flow.
- **Budget `_page`** (`ui/routes/budget.py:44`, 369 lines):
  - It recomputes the 3- and 6-month category averages and the share of income, which `BudgetService` already has.
  - Its first `background_totals` loop (159-167) is overwritten at 175-182, and `category_amounts` (line 123) is never used.
  - It calls the private `c.budgets._owned_spending`.
- **Investments `_page_extras`** recomputes the holdings value and the gain and weight per class.
- **Register.**
  - `register.create_investment_entry` is 171 lines and opens its own transaction.
  - `register.page` has a radon complexity of 119.
  - `register.py:401` builds `OtherAssetValuationRepository` directly.
- **Unused keynotes.** `keynotes.lowest_point`, `next_payment`, `largest_part`, `sale_cost` and `cash_share` compute figures and are unused (9L).

## Fix
- Delete what no template reads.
- Move what screens use into the service the figures registry names, and move the investment entry into a workflow.
- Stay out of 3W's claimed templates and `ui/status.py` while that claim stands.
- Test: cached and uncached HTML stay identical (`tests/test_reporting_performance.py`).
