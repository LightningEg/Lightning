---
title: Phone screens break Part C - cut words, overlapping text, no way back on five pages, small targets, five Settings tabs
type: polish
area: phone
status: ready
created: 2026-10-20
by: Claude
skills: guideline-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§4 Phone) at 390 and 360 px with touch. The high ones are 3R. `tools/phone_check.py` passes, but
`.phone-content` has `overflow-x:hidden`, so clipped items never scroll and the check cannot see them.

1. **Cut words (C12).** Reserves "covers 0.6 months" cut to "0.6 n" (390) and "0." (360); Investments' "By market" chip; Currencies' "Custom" (320);
   the Planner form (320). Cash › Plan headings lose their first letter: `.phone-flat-rows` has `overflow:auto` and no padding.
2. **Overlapping text.** Cash › Recurring: "Possible early/changed payment — review" over "North Cairo Electricity".
   Shot: [phone-recurring-text-overlap.png](../../reports/audit-1/phone-recurring-text-overlap.png). Overview rows: "›" on its own line and a stray "▾" inside "Net ▾flow".
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
