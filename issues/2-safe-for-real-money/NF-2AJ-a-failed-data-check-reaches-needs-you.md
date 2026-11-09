---
title: A failed data check reaches Needs you - today a check that reads ISSUE is visible only to someone who opens Settings › Data checks
type: feature
pillar: protect
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
---

## Report
Found by [r31](../1-easy-to-contribute/r31-code-review-and-loose-ends/report.md) F12. `lightning/integrity.py:IntegrityService.checks` reconciles the ledger against what the screens show (eight checks on the sample: no cash account below zero, budget actual equals categorized spending, free cash matches the ledger, the month-to-date net-worth bridge, units held match the ledger, nothing sold that was not held, and more). Its only reader is `/checks`, a tab under Settings. `grep -n "integrity\|/checks" lightning/workflows/review.py lightning/workflows/reminders.py lightning/ui/routes/dashboard.py` prints nothing: an ISSUE never reaches the Overview, Needs you, the weekly review or a reminder. People may keep real money in Lightning (owner, 2026-10-28); the feature that can say "a figure is wrong" should not wait to be found.

Cost measured: `/checks` takes 86 ms and 88 queries on the sample, so it cannot run on every page.

## Fix
1. `lightning/workflows/review.py:ReviewInbox.items` (line 126): after the existing sources, add one item per check whose status is `ISSUE` (not `INCOMPLETE`, which already shows as Missing valuation): `{"label": "A data check does not add up", "detail": check.name, "priority": 0, "href": "/checks", "action": "Review"}` plus the keys neighbouring items carry (read three of them first: `job`, grouping). Add `"/checks"` to the `prices` group prefixes or a new group, and to the `risk` consequence, following how `/investments/prices` is placed.
2. Keep it cheap: call `c.integrity.checks(on)` only from `items()` (the Overview and Needs you already call `items()` once per request) and decorate `IntegrityService.checks` with `@request_cached(deep=True)`. Measure with `python tools/perf_check.py`: the Overview must stay under 400 queries; if it does not, do IT-9L2 first, and if still over, compute only the count on the Overview (`any ISSUE`) and the names on `/needs-you`.
3. Arabic: add the label and the action to `lightning/ui/i18n.py` (skill `arabic-check`).
4. Tests: a profile with a forced ISSUE (see how `tests/test_integrity*.py` builds one) shows the row on `/` and `/needs-you` and links to `/checks`; a clean sample shows none; `tests/test_mohab_year.py` passes.

## Done when
A failing check is one tap from Home on the PC and the phone, a passing profile shows nothing new, and the Overview's query count is within budget. Release-note: `protect: if a figure stops adding up, Needs you says so and opens Data checks.`

Opus: it adds a source to the inbox every screen shares, and its cost must be measured, not guessed.
