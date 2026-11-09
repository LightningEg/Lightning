---
title: The investment report reads the whole ledger four times per Overview - 426 ms at 4,400 transactions; a narrower query gives the same report twelve times faster
type: tech
pillar: understand
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
---

## Report
Found by [r31](../1-easy-to-contribute/r31-code-review-and-loose-ends/report.md) F2 and F5. On Mohab's year plus 4,000 invented expenses (4,374 transactions):

| Page | Sample (374 rows) | 4,374 rows | Slowest read |
| --- | --- | --- | --- |
| Overview `/` | 131 ms | 426 ms | `SELECT le.*, ... FROM ledger_entries le JOIN transactions t ...` 4 times, 82 ms |
| Spending `/birdview/expenses` | 54 ms | 407 ms | the same read 4 times, 186 ms |
| Investments | 120 ms | 237 ms | the same read twice, 44 ms |

`lightning/investments/report.py:build_investment_report` (line 167) loads every posted ledger line up to `end` and loops over them in Python, though it uses only lines of transactions that touch an investment, deposit or gam'eya account or a non-cash asset. `investment_period` calls it twice (closing and opening), and a page calls `investment_period` once or twice.

Proof that a narrower read is safe: `python issues/1-easy-to-contribute/r31-code-review-and-loose-ends/evidence/investment_query.py` adds one condition and compares `repr()` of the whole report on Mohab's year, the demo household and the 4,374-row profile over five periods each: identical every time, 61 ms down to 4 ms per period.

Second, smaller read: `ReportQueries.asset_purity` (`lightning/reporting/queries.py:349`) runs 39 times on the Overview and 60 on the phone's Investments, with no memo.

## 9L1 Read only the transactions the report uses · M
Files: `lightning/investments/report.py` lines 167-200 only; new test in `tests/test_reporting_performance.py`.
Do: after `balance_ids` is computed, build `portfolio_ids = investment_account_ids | balance_ids` (the name is already used further down: move that line up and reuse it). Add to the `WHERE` of the big query:
`AND le.transaction_id IN (SELECT x.transaction_id FROM ledger_entries x JOIN financial_assets fa ON fa.id=x.asset_id WHERE fa.is_cash=0 OR x.account_id IN (<one ? per portfolio id>))`
and pass the ids as parameters after `end` (sorted, so the SQL text is stable). Delete the unused `placeholders` variable but keep its early return (`if not investment_account_ids: return {...}`). Change nothing else: not the loops, not `_realized_between`.
Test: copy the comparison from `evidence/investment_query.py` into a test: keep the old query text in the test as a helper, run both on the sample and the demo for the five periods, assert `repr(old) == repr(new)`. Then `python -m pytest tests/test_reporting_performance.py tests/test_investments*.py tests/test_mohab_year.py -q` and skill `number-audit`.
Done when: the test passes and `evidence/scale.py 4000` shows the Overview under 330 ms on the same machine (it was 426).

## 9L2 Memo the purity read · S
Files: `lightning/reporting/queries.py:349`.
Do: put `@request_cached` on `asset_purity` (the decorator is imported at the top of the file; the argument is an int and the result an int or None, so no `deep=True`).
Test: `python tools/perf_check.py`: the Overview drops from 375 queries to about 340 and Investments from 184 to about 145; page text unchanged (`tests/test_reporting_performance.py::test_main_tabs_read_each_figure_once_and_show_the_same_pages_as_without_the_cache`).

## 9L3 One investment period per request · S
Files: `lightning/investments/report.py:investment_period`.
Do: after 9L1, check with `evidence/scale.py 4000` whether the big read still runs more than twice on the Overview. If it does, the same `(start, end)` is being asked twice: wrap the body in a module-level helper decorated `@request_cached(deep=True)` keyed on `(start, end)` only if `db`, `accounts`, `assets`, `reporting` are hashable (they are plain objects, so they are); otherwise leave it and say so. Never cache across requests.
Done when: measured before and after are in the commit's `Detail:` line.

Release-note (9L1): `understand: the Overview and Spending stay fast on a long history.`

**With this done, IT-9A stays blocked:** its gate (a tab past 400 ms) was this one read, not missing stored figures.
