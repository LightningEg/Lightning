---
title: Human dates on screens and ج.م in Arabic, as the owner decided on 2026-11-08
type: polish
pillar: understand
size: S
model: opus
status: parked
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F21; owner decisions in the Decided section of this item (they were OW-3BJ). Screens show `2026-11-01 to 2026-11-08`, `until 2026-12-01` and, in Arabic, `٢٠٢٦-١٢-٠١` ([PC](r28-international-polish/evidence/shots/pc-en-home.png), [phone, Arabic](r28-international-polish/evidence/shots/phone-ar-home.png)); Arabic pages label money "EGP" 243 times.

## Fix

Guideline first (both repos), then one set of date filters used everywhere, then the currency label. Fields, files and exports keep `yyyy-mm-dd`.

## Decided

- 2026-11-08, owner (OW-3BJ, finished): dates human on screens, ISO in fields and exports; ج.م for EGP in Arabic; the Arabic period chip in Arabic-Indic digits; rows drop ".00" on the PC as on the phone (cents show when there are any); the Arabic percent sign ٪; dark stays with the themes (A15 unchanged); Arabic addresses the person in neutral forms where a sentence allows.

## Built · 2026-11-10 (O9, Claude)

- 3BK1 in this repo: guideline 3.41 (A06.1, A06.2 in `app.html` and `app-ar.html`, `brand-voice.md` Numbers and Arabic).
- 3BK2-3BK4: `lightning/ui/date_text.py` (`day_text`, `month_text`, `range_text`, filters `day`, `month`, `day_range`; `tests/test_date_text.py`). Instead of editing each template, `human_dates` runs once over every rendered PC and phone screen in `web.render`, so dates written by Python sentences ("until 2026-12-01", "Due 2026-10-03") change too. Text and title/aria-label/data-tip only; fields, links, scripts, typed notes and SVG axes keep ISO; references such as `OUT-2026-08-12-001` are not dates. Tests read an expectation's ISO date as the screen says it (`tests/screens.py` `Screen.said`, `said`).
- 3BK5, 3BK7: `i18n.arabic_marks` in `localize_html`: ج.م for EGP (`currency_label`), ٪ after a figure; `arabic-numbers.js` writes ٪; `tests/test_arabic_number_display.py`.
- 3BK6: `amount_role('row')` drops ".00" on both devices; `tests/test_number_format.py`.
- 3BK8: Arabic values in `i18n.py`, `i18n_system.py`, `journal_i18n.py`, `journal_enrollment_i18n.py`, `starter_workbook.py` use verbal nouns and neutral forms (اختار/اكتب: 467 → 0).

## How to work on this item

## 3BK9 The website's copy of guideline 3.41, and a native reader · S · sonnet · #429
The O9 session could not attach `Lightning_website` (permission denied). Read `skills/website-sync/SKILL.md`; copy `guideline/app.html`, `app-ar.html`, `phone.html`, `phone-ar.html`, `website.html`, `website-ar.html`, `coders.html` and `brand-voice.md` to the website repo's `guideline/` (`cmp` must pass) and open its PR. Then have a native Egyptian reader check a sample of the 3BK8 wording (skill `arabic-check`).
Done when: `python -m pytest tests/test_docs_structure.py -q` passes with the website repo beside this one, and the website PR is merged.
