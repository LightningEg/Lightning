---
title: Arabic search and sorting in the register, one week start, one clock
type: tech
pillar: everywhere
size: M
status: new
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
