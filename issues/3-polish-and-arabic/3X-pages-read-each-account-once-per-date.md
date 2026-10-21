---
title: Pages run one query per account and date, so they slow as accounts are added
type: tech
area: performance
status: ready
created: 2026-10-21
by: Claude
skills: perf-check
app_version: 1.3.0
commit: 6a0bf77
repo: app
---

## Report
Found when Mohab's sample gained three accounts (7 to 10): the Overview ran 817 reads instead of 790, Cash planning 536 instead
of 400, Holdings 310 instead of 290. Not repeats (the request cache holds): each page asks the same per-account figures
(cash held for others, gold grams, prices, rates) once for every account and every date it draws. The test budgets in
`tests/test_reporting_performance.py` were raised to match.

## Fix
Read those figures for all accounts in one query per date (or per range), as the register already does for owners. Keep every
output identical (the test compares the cached and uncached pages), then lower the budgets again.

## Investigation
Claude, [Audit 3](../../reports/audit-3.md) §1, perf-check.

**Call chains.**
- `dashboard` → `visuals.net_worth_trend` (10–12 month ends) → `PositionService._at` → `class_values`/`owned_holdings` → `cash_total_for_account`: 2 SQL per cash holding (`planning/position.py:218`).
- `_at` → `reporting.owned_brokerage_cash` → `_owned_brokerage_cash_by_account`: 3 SQL per brokerage per date (`reporting/service.py:340`).
- Cash planning comes the same way through `visuals.cash_plan` (5 month ends, only for `free_cash`), `forecast.free_cash` and `zakat.assess`.
- The per-account loop is copied in `dated_cash.py:99`, `funding.py:64`, `foreign_currency_accounts` and `_balance_and_owned`.

**Batching.** `MoneyFromOthersService.totals_by_account(day)` already exists. Request-cache it, and add `ReportingService.owned_cash_by_account(day)`: one cash `GROUP BY account_id` plus those totals. Point all six callers at it. A `free_cash_at(day)` (like `portfolio_value_at`) also saves the holdings-by-class reads in `cash_plan`.

**Measured.** A monkeypatched prototype, on top of 3Y's fix, with identical HTML: Overview 445 → 353, Cash planning 263 → 199, Financial health 233 → 176. 3Y is done (test page budgets lowered); lower them again after this.
