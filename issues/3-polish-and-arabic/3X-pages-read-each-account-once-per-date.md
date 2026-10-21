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
