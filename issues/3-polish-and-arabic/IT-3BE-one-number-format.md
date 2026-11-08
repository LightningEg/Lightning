---
title: One number format on screen - the browser follows the app, not the Windows locale, and every negative uses a true minus
type: tech
pillar: understand
size: S
status: new
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
