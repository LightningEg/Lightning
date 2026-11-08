---
title: Human dates on screens and ج.م in Arabic, as the owner decided on 2026-11-08
type: polish
pillar: understand
size: L
model: opus
status: ready
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F21; owner decisions in [OW-3BJ](OW-3BJ-international-display-decisions.md). Screens show `2026-11-01 to 2026-11-08`, `until 2026-12-01` and, in Arabic, `٢٠٢٦-١٢-٠١` ([PC](r28-international-polish/evidence/shots/pc-en-home.png), [phone, Arabic](r28-international-polish/evidence/shots/phone-ar-home.png)); Arabic pages label money "EGP" 243 times.

## Fix

Guideline first (both repos), then one set of date filters used everywhere, then the currency label. Fields, files and exports keep `yyyy-mm-dd`.

## How to work on this item

Each step is one pull request, in order. Read only the files a step names. Delete the step's heading in the same commit.


## 3BK1 Guideline: human dates on screens · M
Owner decision 2026-11-08 ([OW-3BJ](OW-3BJ-international-display-decisions.md)). Read `skills/website-sync/SKILL.md` first: a guideline change lands in this repo and in `Lightning_website` in the same session, with a PR in each, and `cmp` must pass.
Files: `guideline/app.html` A06.1 and A06.2 (print them with `python tools/guideline.py A06`; edit only those blocks), `guideline/phone.html` C10 if it repeats the date rule, `guideline/brand-voice.md` "Numbers" line (~36), `guideline/app-ar.html` A06.2.
Do: replace "2026-09-30 · 2026-09 · ranges with "to"" and the crossed-out "30 Sep 2026" with: screens show `8 Nov` (this year), `8 Nov 2025` (other years), `November 2026` (a month), `1–8 Nov` (a range), `Today`/`Yesterday` for the last two days; fields, files and exports keep `2026-11-08`. Arabic: `٨ نوفمبر`, `نوفمبر ٢٠٢٦`, `النهارده`/`امبارح`, Egyptian month names as today.
Done when: `python -m pytest tests/test_docs_structure.py -q` passes with the website repo present beside this one, and both PRs are open.

## 3BK2 The date filters, tested alone · M · sonnet
Needs 3BK1 merged first.
Files: `lightning/core/dates.py`, `lightning/ui/web.py` (beside `_day_label` ~190; register filters beside `templates.env.filters["money"]` ~134), `lightning/ui/i18n.py` (the Egyptian Arabic month names already there).
Do: pure functions `day_text(d, locale, today)` → "Today", "Yesterday", "8 Nov", "8 Nov 2025"; `month_text(d, locale)` → "November 2026"; `range_text(start, end, locale, today)` → "1–8 Nov", "28 Oct – 8 Nov", "Dec 2025 – Jan 2026". Arabic: "النهارده", "امبارح", "٨ نوفمبر", "نوفمبر ٢٠٢٦" (digits via the existing Arabic number path). Register them as Jinja filters `day`, `month`, `day_range`. Change no template yet.
Done when: new `tests/test_date_text.py` covers each output above in both languages, year boundaries, and `today` taken from `LIGHTNING_TODAY`. `python -m pytest tests/test_date_text.py -q`.

## 3BK3 PC screens use them · M · sonnet
Needs 3BK2 merged first.
Files: the PC templates from `grep -rln "date\b\|period\|\.month" lightning/ui/templates --include=*.html | grep -v phone/` that print a date as text: the page header line (`2026-11-01 to 2026-11-08`), the period chip (`2026-11`), KPI chips (`until 2026-12-01`, `2026-11 so far`), Needs you rows, chart captions (A12; axes may stay short), and the register's Date column.
Do: use the filters; inputs (`<input type=date|text name=date>`) keep ISO. If the diff passes ~400 lines, stop and split this step by section (Overview/Budget/Cash planning first, then the rest).
Done when: rerunning `python issues/3-polish-and-arabic/r28-international-polish/evidence/probe.py` shows no `yyyy-mm-dd` in `dates` for any PC page, and `python -m pytest tests/test_mohab_year.py -q` passes (update its date assertions to the new text).

## 3BK4 Phone screens use them · M · sonnet
Needs 3BK2 merged first.
Files: `lightning/ui/templates/phone/` (`grep -rln "date\|month" lightning/ui/templates/phone`).
Do: as 3BK3, for Home ("On top of your plan until 1 Dec."), Latest/Activity day headers (after Yesterday comes "5 Nov", not `2026-11-05`), Bills, Report and the month stepper.
Done when: the probe shows no `yyyy-mm-dd` on phone pages and `python -m pytest tests/test_mohab_phone.py tests/test_phone_check.py -q` passes.

## 3BK5 Arabic currency label ج.م · S · sonnet
Owner decision 2026-11-08 ([OW-3BJ](OW-3BJ-international-display-decisions.md)). Needs 3BK1 merged first. Its guideline PR also changes the A06.2 currency line.
Files: `lightning/ui/i18n.py` (keys with "EGP", and the few that say جنيه), the macro that prints the currency beside big figures (`lightning/ui/templates/partials/macros.html` lines ~2-7), `lightning/ui/static/arabic-numbers.js` only if it rewrites "EGP".
Do: on Arabic pages the code EGP shows as ج.م; other currencies keep their code (USD, SAR). Do it in one place: a `currency_label(code, locale)` helper used by the macro and by `translate` for `{cur}` values.
Done when: the r28 probe's Arabic pages contain no "EGP" in visible text, and `python -m pytest tests/test_arabic_number_display.py tests/test_arabic_no_english.py -q` passes.
