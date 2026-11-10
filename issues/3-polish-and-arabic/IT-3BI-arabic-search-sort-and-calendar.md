---
title: Arabic search and sorting in the register, one week start, one clock
type: tech
pillar: everywhere
size: M
model: sonnet
status: ready
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F19-F20.

- Global search folds hamza, ة/ه, ى/ي, diacritics and digits (`core/matching.py:33 fold_search_text`), but the Transactions search uses plain SQL `LIKE` (`transactions/repository.py:63-70`): "احمد" does not find "أحمد", and categories are matched by their English names only.
- Sorting by code point or `COLLATE NOCASE` (`planning/repository.py:35`, `reporting/service.py:420`); `localeCompare` without a locale (`app.js:1712,1801`).
- The heatmap week starts on Saturday (`visuals.py:247`), the date picker on Monday (`app.js:652`).
- 7 naive `datetime.now()` and 4 `date.today()` bypass `core/dates.today()` (`routes/sms.py:92`, `sms_imports.py:125,408`, `desktop/window.py:82`).

## Fix

Register a SQLite function `fold(text)` from `fold_search_text` and search folded columns (and the localised category name); sort names with a fold-then-locale key; pass `document.documentElement.lang` to `localeCompare`; one week-start setting (Saturday by default for Egypt) used by both; route every "now" through `core/dates`. Tests: register search finds أحمد from احمد and Arabic category names; a grep test forbids naive `datetime.now()` outside `core/dates`; run skill perf-check on the register.

## How to work on this item

Each step is one pull request. Read only the files a step names. Run the step's test command and `python -m pytest tests/test_search_arabic.py -q`; delete the step's heading in the same commit.

## 3BI2 Names sort the Arabic way · S · #405
Files: `lightning/planning/repository.py:35`, `lightning/reporting/service.py:420`, `lightning/ui/static/app.js:1712,1801`.
Do: in Python, sort lists of names with `key=lambda n: fold_search_text(n)` after fetching (not in SQL); in JS, `a.localeCompare(b, document.documentElement.lang, {sensitivity: "base"})`.
Done when: a test sorts ["إيمان", "احمد", "Zed", "ahmed"] the same way both places (folded order) and `grep -n "localeCompare(" lightning/ui/static/app.js` shows a locale argument on every call.

## 3BI3 One week start · S · #406
Files: `lightning/ui/visuals.py` (~line 247, the heatmap's first weekday), `lightning/ui/static/app.js` (~line 652, the date picker).
Do: a constant `WEEK_STARTS = 5` (Saturday, Python's `weekday()` numbering) in `lightning/core/dates.py`, used by the heatmap; pass it to the page (a `data-week-start="6"` attribute on `<html>` in both bases, JS `getDay()` numbering, where Saturday is 6) and have the date picker read it.
Done when: a test renders the date picker on `/accounts/1/transaction/new` and finds Saturday as the first column header, and the heatmap test (find it: `grep -rln "heatmap" tests`) still passes.

## 3BI4 One clock · S · #407
Files: `lightning/ui/routes/sms.py:92`, `lightning/sms_imports.py:125,408`, `lightning/desktop/window.py:82`, and the rest from `grep -rn "datetime.now()\|date.today()" lightning --include=*.py`.
Do: use `lightning.core.dates.today()` for dates and add `now()` beside it (honouring `LIGHTNING_TODAY` for the date part) for timestamps; replace each call. Leave sync/journal timestamps that must be real wall-clock time, and say so in a comment.
Done when: a new test greps `lightning/` and allows `datetime.now(`/`date.today(` only in `core/dates.py` and a short allowlist of journal files.
