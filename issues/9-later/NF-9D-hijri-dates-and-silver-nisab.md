---
title: Hijri dates, and the silver nisab for zakat
type: feature
pillar: own
size: M
model: opus
status: new
created: 2026-10-19
by: Claude
---

## Report
Arabic and zakat are built without them. Checked 2026-11-08 against the code:

- **Zakat day is Gregorian only.** `lightning/zakat.py` `zakat_days(first_day, on)` adds `LUNAR_YEAR_DAYS = 354` to the date the user picked; the zakat pages (`lightning/ui/templates/zakat.html`, `phone/zakat.html`) and the gear (`settings/zakat_section.html`) show and take a `yyyy-mm-dd` date. A true lunar year is about 354.37 days, so +354 drifts about one day every three years from the Hijri date the user meant. Nothing in `lightning/` converts to or from Hijri (`grep -rni hijri lightning` is empty). The tab-by-tab review asks for it too: [IV-3H](../12-desktop-ux/IV-3H-tab-by-tab-review.md) ZK-1 ("Offer 1 Ramadan this year and show the Hijri date beside the Gregorian").
- **Nisab is gold only.** `ZakatService.nisab()` is `NISAB_GRAMS = 85` × `gold_price_24k(day)`, else the nisab the user typed (`zakat_settings.typed_nisab_e6`, migration `0054_zakat.sql`). The common silver nisab (595 g of pure silver) is not offered. Silver can now be held (asset kind `SILVER`, code prefix `SLV`, `lightning/assets/domain.py:114`, migration `0076_silver_class.sql`) but is priced by hand: there is no silver reference price like `REF:GLD-24K`, and `lightning/market/sources/yahoo.py:41` maps `XAG/USD` to `SI=F` without any caller.
- Architecture › Zakat, Glossary › Zakat day and Overview §shipped all say "Hijri dates are not built" and "A silver nisab is not built"; each step below updates the line it makes untrue.

## Fix
After the owner's two decisions (9D1, 9D2): a Hijri conversion in Python (`lightning/core/hijri.py`), the Hijri date shown beside every zakat day, the zakat day optionally kept on its Hijri date, and a nisab basis setting (gold, silver, or the lower of the two) with a silver gram price. Money logic stays in `lightning/zakat.py`; templates only draw.

## How to work on this item

Each step below is one pull request. Read only the files a step names (`grep -n` before reading `lightning/zakat.py` whole). Run the step's test command, then `python -m pytest tests/test_zakat.py tests/test_issues.py -q`; for a visible change also `python -m pytest tests/test_mohab_year.py -q`. Delete the step's heading in the same commit, and record the owner's answers in this file and in `ai/PROJECT_OVERVIEW.md` owner decisions.

## 9D1 Owner: which Hijri calendar, and does the zakat day follow it · owner
Two questions, asked as one pick-list each:
1. **Where Hijri dates come from, offline.** (a) *(Recommended)* The Umm al-Qura table through the small pure-Python package `hijridate` (MIT; tables for 1343-1500 AH, no network): exact for Saudi official dates; Egypt's Dar al-Ifta sighting can differ by one day, so the screen says "about". Needs a new dependency on Windows and Android. (b) The same Umm al-Qura month starts copied into Lightning as data: no dependency, but we own its provenance and updates. (c) The arithmetic (tabular) Islamic calendar: a few lines of Python, no data, but often one to two days off the announced date.
2. **What the zakat day follows.** (a) *(Recommended)* The user may pick it as a Hijri date (e.g. 1 Ramadan); each next zakat day is that Hijri date in the next Hijri year; a day picked as Gregorian keeps +354 days as now. (b) Always +354 days, the Hijri date only shown: simplest, drifts a day every three years. (c) Always the Hijri anniversary, existing Gregorian picks converted once.

## 9D2 Owner: which nisab by default, and where the silver price comes from · owner
1. **Nisab basis.** (a) *(Recommended)* Gold (85 g of 24K) stays the default; Settings offers *Silver (595 g)* and *The lower of the two*; the page names the basis. (b) Silver by default: more people owe zakat, which many scholars advise for the poor's benefit, but it changes every existing estimate. (c) The lower of the two by default. Either way the page keeps "a scholar answers your own case".
2. **Silver price.** (a) *(Recommended)* The user types a gram price of pure silver behind the gear, kept with its date (as the typed nisab is); no network. (b) A seeded reference `REF:SLV-999` priced from Yahoo's world price (`SI=F` ÷ 31.1035 × `EGP=X`), like gold's world price in `lightning/workflows/live_prices.py`: automatic, but an Egyptian shop price differs and it adds a price job. (c) The newest price of a silver holding the user owns: none for most people.

## 9D3 Hijri conversion in Python · S · opus
Needs 9D1 decided first.
Files: new `lightning/core/hijri.py`; new `tests/test_hijri.py`; for option 1(a) also `pyproject.toml` `dependencies`, `requirements/android.in` and the locks, following `skills/dependency-change/SKILL.md`.
Do: two functions only: `to_hijri(day: date) -> tuple[int, int, int]` (year, month 1-12, day) and `from_hijri(year: int, month: int, day: int) -> date`, using the source the owner chose; raise `ValidationError` (from `lightning/core/errors.py`) outside the supported range with a readable sentence. Plus `HIJRI_MONTHS_EN` and `HIJRI_MONTHS_AR` (Muharram … Dhu al-Hijjah / محرم … ذو الحجة).
Done when: `tests/test_hijri.py` asserts 2026-02-18 ↔ 1 Ramadan 1447 and 2026-03-20 ↔ 1 Shawwal 1447 (check both against the chosen source first, and write in the test which source they come from), a round trip for every first-of-month from 1445 to 1450, and the out-of-range error. `python -m pytest tests/test_hijri.py -q`; on option 1(a) also the dependency skill's own checks.

## 9D4 Show the Hijri date beside every zakat day · S · sonnet
Needs 9D3 merged first.
Files: `lightning/ui/web.py` (filters near line 134), `lightning/ui/templates/zakat.html` (lines 6, 22, 30, 47), `lightning/ui/templates/phone/zakat.html` (lines 5, 31, 39, 42), `lightning/ui/templates/settings/zakat_section.html` (line 8), `lightning/ui/i18n.py` `ARABIC_UI`.
Do: add a filter `templates.env.filters["hijri"]` that takes a `yyyy-mm-dd` string and the locale and returns `"1 Ramadan 1447"` (English) or `"1 رمضان 1447"` (Arabic) from `lightning.core.hijri.to_hijri`; empty string on `None` or out of range. Where a template prints `a.zakat_day` or `a.previous_day`, add `<small>` with `'about {hijri}'|tr(locale, hijri=a.zakat_day|hijri(locale))` beside it; under the gear's date field show the Hijri date of the saved day. Add `'about {hijri}': 'نحو {hijri}'` to `ARABIC_UI`. Change no service or figure.
Done when: `tests/test_zakat.py` gains `test_the_zakat_day_shows_its_hijri_date` (copy the client set-up of `test_the_page_works_on_a_phone_and_in_arabic`): with zakat day 2026-02-18 the PC page contains "1 Ramadan 1447", the phone page too, and in Arabic "رمضان". `python -m pytest tests/test_zakat.py -q`.

## 9D5 Keep the zakat day on its Hijri date · M · opus
Needs 9D3 merged first, and 9D1 answered (a) or (c) to question 2; on (b) delete this step.
Files: `lightning/zakat.py` (`zakat_days`, `ZakatSettings`, `save_settings`, `assess`, `forecast`), a new migration after the newest in `lightning/database/migrations/` (skill add-migration), `lightning/ui/routes/zakat.py` (`save_zakat_settings`), the three zakat templates, `ai/ARCHITECTURE.md` › Zakat, `ai/GLOSSARY.md` › Zakat day.
Do: store how the day was picked (`zakat_settings.zakat_day_calendar` `'gregorian'|'hijri'`, default `'gregorian'`, plus the Hijri month and day when `'hijri'`); `zakat_days` returns the previous and next Hijri anniversaries for a Hijri pick and keeps +354 for a Gregorian one. The gear and the first-time form offer "Pick a Hijri date" (month list and day). *Paid this zakat year* uses the same window, so check `paid_between` callers. Audit row as today.
Done when: new tests in `tests/test_zakat.py`: a Hijri pick of 1 Ramadan gives 2026-02-18 then the Gregorian date of 1 Ramadan 1448 from the chosen source; a Gregorian pick still gives +354; a payment between the two days lowers Still to pay; an upgrade test opens a profile at the previous schema and keeps its day as Gregorian. `python -m pytest tests/test_zakat.py tests/test_migration_safety.py -q`.

## 9D6 Silver nisab in the zakat service · M · opus
Needs 9D2 decided first.
Files: `lightning/zakat.py` (`NISAB_GRAMS`, `ZakatSettings`, `nisab()`, `Assessment.nisab_source`), a new migration after the newest (skill add-migration), `lightning/core/figures.py` (the `nisab` figure's meaning), `tests/test_zakat.py`, `ai/ARCHITECTURE.md` › Zakat.
Do: add `NISAB_SILVER_GRAMS = Decimal(595)`; settings `nisab_basis` (`'gold'|'silver'|'lower'`, default per 9D2) and the silver gram price per 9D2 (typed: `typed_silver_e6` and its date, like `typed_nisab_e6`); `ZakatService.silver_price(day)`; `nisab()` returns `(amount, source, date)` with source `"silver"` or `"lower"` as chosen, falling back exactly as gold does today (typed nisab, then none with a reason, never zero). Regenerate the Glossary with `python -m lightning.core.figures`.
Done when: new tests: silver basis gives 595 × the silver price; lower basis picks the smaller of gold and silver; a missing silver price with silver basis gives no estimate and a reason; the default basis leaves every existing `tests/test_zakat.py` test passing unchanged. `python -m pytest tests/test_zakat.py tests/test_figures_layer.py -q`.

## 9D7 The gear and the page name the nisab basis · S · sonnet
Needs 9D6 merged first.
Files: `lightning/ui/templates/settings/zakat_section.html`, `lightning/ui/routes/zakat.py` (`save_zakat_settings`: read `nisab_basis` and the silver price from the form and pass them to `save_settings` as 9D6 named them), `lightning/ui/templates/zakat.html` line 27 and `phone/zakat.html` line 37 (the nisab `<small>`), `lightning/ui/i18n.py` `ARABIC_UI`.
Do: in the gear, three radio choices *Gold (85 g)*, *Silver (595 g)*, *The lower of the two* (soft wells, no dropdown: guideline A16 "Dropdown for your data"; check `python tools/guideline.py A10`), and the silver gram price field when 9D2 chose a typed price. On the page, the nisab `<small>` says `'595 g of silver at the price of {date}'` for silver and `'The lower of gold and silver, {date}'` for lower. Add each new English string with its Arabic to `ARABIC_UI`.
Done when: `tests/test_zakat.py` gains `test_the_gear_saves_the_nisab_basis` (post the form as `test_the_gear_saves_the_settings_and_the_first_time_form_keeps_the_rest` does; assert the setting and the page's small line on PC, phone and Arabic). `python -m pytest tests/test_zakat.py tests/test_arabic_no_english.py -q`.
