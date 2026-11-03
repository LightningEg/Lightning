---
title: Routes still compute figures, some that no screen shows
type: tech
pillar: build
size: M
status: ready
post: no
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 5](../../reports/2026-10-21-backend-streamlining/report.md) §4. This breaks the rule "Routes never compute figures" (Architecture › Three layers).

Done (2026-10-22): the Overview's eight unread figures are gone; Budget reads its averages, background estimates and tracking suggestions from `BudgetService`; Investments weighs holdings against `Position.holdings_value`; the investment entry is `workflows/investment_entry.record`; the Other asset value comes from `AccountService.manual_value`. Left:

- **Investments `_page_extras`** still sums each class's lifetime gain from `Holding.owned_result`; no service has that figure. The investment report's `value` (738,486 on Mohab, 2026-10-02) is 14,000 below the Holdings value the page and Position show (752,486): the gap is the Office gam'eya, which the report counts at −14,000 and Position leaves out. That gap is intended (5I, decided 2026-11-02: the owed circle stays below zero on Investments, labelled and linked; `tests/test_demo_and_visuals.py::test_an_owed_circle_is_labelled_and_linked_to_what_you_owe_in_the_sidebar`), so the page must not switch to the report's `value`; only the lifetime gain per class still needs a service figure.
- **`register.page`**: split on 2026-11-02 into `_period_filters`, `_category_filter`, `_account_holdings` and `_edit_original` (no behaviour change; radon was not installed to re-measure the 119).
- ~~`ui/routes/accounts.py`~~ done (2026-11-02): the Other asset value is saved by `AccountService.save_other_asset_value` (`tests/test_architecture.py::test_other_asset_value_is_saved_through_the_account_service`).

## Fix
- Move what screens use into the service the figures registry names.
- Test: cached and uncached HTML stay identical (`tests/test_reporting_performance.py`).

**Not posted to contributors (2026-10-31):** what is left needs the owner's decision on how the gam'eya circle counts, and touches routes under active declutter work.
