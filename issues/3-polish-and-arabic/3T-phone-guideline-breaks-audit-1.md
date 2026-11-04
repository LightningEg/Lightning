---
title: Phone screens break Part C - cut words, overlapping text, no way back on five pages, small targets, five Settings tabs
type: polish
pillar: feel
size: L
status: ready
post: no
created: 2026-10-20
by: Claude
skills: guideline-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§4 Phone) at 390 and 360 px with touch. The high ones are 3R. `tools/phone_check.py` passes, but
`.phone-content` has `overflow-x:hidden`, so clipped items never scroll. The checker now detects content clipped past the viewport (3T7).

1. **Cut words (C12).** Reserves "covers 0.6 months" cut to "0.6 n" (390) and "0." (360); Investments' "By market" chip; Currencies' "Custom" (320);
   the Planner form (320). Cash › Plan headings lose their first letter: `.phone-flat-rows` has `overflow:auto` and no padding.
2. **Overlapping text.** Cash › Recurring: "Possible early/changed payment — review" over "North Cairo Electricity".
   Shot: [phone-recurring-text-overlap.png](../../reports/2026-10-20-demo-readiness/evidence/phone-recurring-text-overlap.png). Overview rows: "›" on its own line and a stray "▾" inside "Net ▾flow".
3. **No way back (C03.4).** /sms, /search, /accounts/N/import, /investments/planner and /settings show the logo, not "‹ page". A Budget category opens
   Transactions under Accounts with "‹ Accounts", losing Budget.
4. **Budget category → Transactions (C08.3, A16).** A full-screen filter card comes before any row; it reads "Personal › Eating Out"; two period controls.
5. **Search (C12).** Says "Press Ctrl K on any page"; not live; results sit in a card.
6. **Targets under 48 px (C05.1).** Period ‹ › 25×44 (8×44 in Export for AI); quiet links 19–22 tall (Weekly review, Review activity, Pay early, How free
   cash is built); "Show the numbers" 117×32; "Add a reserve" 20 tall; "1 due" chips 50×24; "Aliases" 41×12. Picker options 38 tall, and the picker
   list is 348 px wide from x=40 on a 360 screen, so its edge is cut.
7. **Settings has five tabs (C03.3)**, and its tables are stacked rows with "Setting / Value" repeated: still a table.
8. **Money first (C01.1).** Overview "Latest": three of six rows are green "+7,090.00 Investment revaluation"; the register hides these behind "Show value updates".
9. **Expense analysis.** Two charts in one card, bordered tiles in a card; lower spending "−20,272 · 86%" is Ink, C06.3 says green.
10. **Charts (C07.1, A16).** Time axes with 8–10 labels (3 allowed); legends above charts; five or more names without Other (Investments donut and
    Biggest holdings, Reserves "Could also use", Planner); the Currencies chart is mostly empty.
11. **Fields (C05.1, C09.2).** 15 px text (budget limits 13 px), rule is 16; the focus fill is cream, A10 says a deeper well with a green edge.
12. **Pairs and alone.** Overview Investing rate and Left in plan have no comparison; "10% used" wraps at 360; Loans and Recurring KPIs sit alone; Import
    "Review statement | Cancel" and Recurring "Track | Not recurring" side by side; an undo pill beside every page action (C04.5).
13. Small: Profiles reuses the PC wordmark and Language select; Prices says "another computer"; "Date yyyy-mm-dd" hints; Zakat's date shows mm/dd/yyyy;
    "3,021.5 EGP"; Loans uses Overview's house icon; /profiles has no favicon.

## Fix
`phone.css` and the `templates/phone/` pages; regenerate `phone.rtl.css`. Make `tools/phone_check.py` also report elements past the screen edge.

3T2 is done: SMS and Search acquired Back in 3AN5/3AN6; Settings, account import and the investment planner now have fallback destinations. Budget category links return to Budget and the rebuilt register has one period control and a concise category filter (`tests/test_phone_frame.py`).

## 3T1 Cut words and overlapping text (C12) · M
Report items 1-2. Verify first: audits 10 and 12 (3AL, 3AM) rebuilt many screens. Reproduce this on the current build; if it is already fixed, delete the step and name the commit that fixed it.

**2026-11-04:** Chromium at 320/360 shows the current Reserves months label and Overview arrows/Net flow uncut (the latter was rebuilt by 3AN12, `89848dc0`). The Planner's choice labels now wrap inside the card (`tests/test_phone_check.py`). The sample had no changed-payment warning, so that overlap and the other reported states still need targeted verification.

## 3T3 Touch targets · M
Report item 6: targets under 48 px (C05.1). The search half (item 5: live search, results in a card, "Press Ctrl K") was built by IV-3AN's 3AN6 (2026-11-02). Verify first: audits 10 and 12 (3AL, 3AM) rebuilt many screens. Reproduce this on the current build; if it is already fixed, delete the step and name the commit that fixed it.

**2026-11-04:** The alias disclosure has a 44 px quiet target, picker choices have 48 px targets and wrap, and the picker is clamped to the viewport (`tests/test_phone_check.py`, 320 and 360 px). The rebuilt period arrows, including Ask an AI, are 48 px; Pay early and Show the numbers are 44 px, loan due buttons are at least 48 px and Add a reserve is 48 px. Other reported targets still need review.

## 3T4 Settings tabs and money first · M
Report items 7-8: five tabs (C03.3), stacked rows still a table, Overview Latest led by revaluations. Verify first: audits 10 and 12 (3AL, 3AM) rebuilt many screens. Reproduce this on the current build; if it is already fixed, delete the step and name the commit that fixed it.

**2026-11-04:** Phone Settings and its related pages now return to More, which already links to each page, instead of showing five tabs (`tests/test_phone_frame.py`). Overview Latest excludes value updates, as the register does (`tests/test_register_folds_and_views.py`). The Settings table layouts still need review.

## 3T5 Charts and expense analysis · M
Report items 9-10: two charts in one card, time axes with 8-10 labels, five or more names without Other.

**2026-11-04:** Shared donut grouping now folds exactly five names (and combines an existing Other); phone time axes show at most three labels. Tests: `tests/test_demo_and_visuals.py` and `tests/test_phone_check.py`. Review the remaining chart and comparison observations before closing.

## 3T6 Fields, pairs and small things · M
Report items 11-13: 15 px field text, focus fill, lone KPIs, Zakat date format, Profiles wordmark.

**2026-11-04:** Phone entry fields, including the profile language selector, now render at 16 px despite desktop overrides; the amount field keeps 24 px. A 320/360 browser sweep and `tests/test_phone_check.py` cover this. Focused phone fields now deepen the theme well towards its focus colour, with a focus-coloured edge; the profile page has its favicon and Prices says “another device” on the phone. Pairs, the Zakat date and the other small observations remain to review.
