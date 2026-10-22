---
title: Routes still compute figures, some that no screen shows
type: tech
area: ui
status: ready
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 3](../../reports/audit-3.md) §4. This breaks the rule "Routes never compute figures" (Architecture › Three layers).

Done (2026-10-22): the Overview's eight unread figures are gone; Budget reads its averages, background estimates and tracking suggestions from `BudgetService`; Investments weighs holdings against `Position.holdings_value`; the investment entry is `workflows/investment_entry.record`; the Other asset value comes from `AccountService.manual_value`. Left:

- **Investments `_page_extras`** still sums each class's lifetime gain from `Holding.owned_result`; no service has that figure. The investment report's `value` (738,486 on Mohab, 2026-10-02) is 14,000 below the Holdings value the page and Position show (752,486): find out which is right before the page reads the report.
- **`register.page`** has a radon complexity of 119.
- **`ui/routes/accounts.py:251`** saves an Other asset value through `c.reporting.other_asset_values`, a repository; move it to `AccountService`.
- **Unused keynotes** are 9L.

## Fix
- Move what screens use into the service the figures registry names.
- Test: cached and uncached HTML stay identical (`tests/test_reporting_performance.py`).
