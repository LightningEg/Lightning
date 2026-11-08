---
title: One number format on screen - the browser follows the app, not the Windows locale, and every negative uses a true minus
type: tech
pillar: understand
size: S
model: sonnet
status: ready
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F7. The server formats money once (`web.py:61`) with a true minus, but:

- `app.js:1391,1443,1526` use `new Intl.NumberFormat(undefined, …)` and `budget.html:83` `toLocaleString(undefined…)`: on a German or French Windows the live totals read "1.234,56" with a hyphen next to the server's "1,234.56"; `:1526` also drops row decimals (`minimumFractionDigits: 0`).
- `ui/kpis.py:294,341` build "-89.5 points" with `f"{gap:+.1f}"`, bypassing `_signed_pct` ([shot](r28-international-polish/evidence/shots/pc-en-home.png), Investing rate).
- Four copies of the same formatter: `ui/keynotes.py:15`, `ui/routes/dashboard.py:20`, `workflows/review.py:24`, `ui/routes/search.py:103`.

## Fix

A single `window.lightningMoney(value, {signed, places})` pinned to `en-US` grouping with U+2212 (Arabic digits still come from `arabic-numbers.js`); use `_signed_pct` in `kpis.py`; delete the copies in favour of `core/money.fmt`. Test: a JS test under a `de-DE` browser locale asserts "1,234.56" and "−"; a grep test forbids `Intl.NumberFormat(undefined` and `:+.1f}` in `lightning/ui`.

## How to work on this item

Each step is one pull request. Read only the files a step names; never open `guideline/app.html` whole (use `python tools/guideline.py A10`). Run the step's test command, then for a visible change `python -m pytest tests/test_mohab_year.py -q` and check A16 on a screenshot; delete the step's heading in the same commit.

## 3BE1 The KPI "points" use a true minus · S
Files: `lightning/ui/kpis.py:294` and `:341`; `_signed_pct` lives in `lightning/ui/web.py` (~line 179).
Do: move `_signed_pct` to `lightning/ui/kpis.py`'s imports (import it from `web.py`, or better move it to `lightning/core/money.py` as `signed_pct` and import it in both), then build `f"{signed_pct(gap)} points"` instead of `f"{gap:+.1f} points"`. Search for the same pattern elsewhere: `grep -rn ':+\.[0-9]f}' lightning/ui`.
Done when: that grep is empty and a test in `tests/test_number_format.py` (new) renders `/` on the sample household and finds no `-` directly before a digit in the KPI row (`.kpi` elements). `python -m pytest tests/test_number_format.py -q`.

## 3BE2 Browser numbers ignore the Windows region · S
Files: `lightning/ui/static/app.js` lines ~1391, ~1443, ~1526; `lightning/ui/templates/budget.html:83`.
Do: add near the top of `app.js` one helper `window.lightningNumber = (value, {min = 0, max = 2, signed = false} = {}) => …` that uses `new Intl.NumberFormat("en-US", {minimumFractionDigits: min, maximumFractionDigits: max})` and replaces a leading `-` with `−` (and adds `+` when `signed` and > 0). Use it at the three `Intl.NumberFormat(undefined` calls (keep each call's fraction digits, except ~1526 which shows money: `min: 2, max: 2`, per A06.1) and the `toLocaleString(undefined` in `budget.html`. Arabic digits still come from `arabic-numbers.js`; do not touch it.
Done when: `grep -rn "NumberFormat(undefined\|toLocaleString(undefined" lightning/ui` is empty; a Node test `tests/number-runtime.test.cjs` (copy `tests/theme-runtime.test.cjs`'s harness) asserts `lightningNumber(-1234.5, {min: 2})` is `"−1,234.50"` with the process run as `LANG=de_DE.UTF-8 node tests/number-runtime.test.cjs`.

## 3BE3 One money formatter in Python · S
Files: `lightning/ui/keynotes.py:15`, `lightning/ui/routes/dashboard.py:20`, `lightning/workflows/review.py:24`, `lightning/ui/routes/search.py:103`.
Do: delete the local `fmt` wrappers and import `fmt` from `lightning.core.money` (same signature). For `search.py fmt_amount`, replace its body with a call to `lightning.ui.web._money` or `core.money.fmt` with a true minus; keep its name if templates call it.
Done when: `grep -rn "^def fmt\|def fmt_amount" lightning --include=*.py` shows only `lightning/core/money.py` (and `fmt_amount` as a one-line delegate if kept). `python -m pytest tests/test_search*.py tests/test_keynote*.py -q`.
