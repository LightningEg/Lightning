---
title: The Arabic bank import preview mixes English into Arabic lines
type: bug
look: visual
severity: low
pillar: feel
size: M
status: ready
created: 2026-11-05
by: Claude Sonnet 5.5
app_version: 1.5.4
repo: app
github: 342
---

## Report
Checked with `lightning.ui.i18n.translate(text, 'ar')`: "To fix" gives "إلى fix"; "Use this category for this counterparty next time" gives "استخدم الفئة دي لـ this counterparty…"; "Select every row of" and "Select line" give "اختار every row of" and "اختار line"; "Possible duplicate", "Counterparty or account", "Link to" and "open the counterparty list and choose it to confirm." have no Arabic entry. Not yet seen on a rendered page: check the preview in Arabic with Mohab's sample first.

## Done when
The bank import preview, drawn in Arabic with Mohab's sample, shows no English words, and `tests/test_arabic_no_english.py` covers the preview page and passes.

Where to look: `lightning/ui/templates/bank_import_preview.html` (lines 12-72) and `lightning/ui/i18n.py`.
Read first: `guideline/website-ar.html` B04 (the Egyptian Arabic voice); `tests/test_arabic_no_english.py`.
