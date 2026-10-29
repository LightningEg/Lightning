---
title: Phone declutter, tab by tab - each tab opens on its answer and its daily action; analysis one tap away
type: polish
area: phone
status: ready
created: 2026-10-29
by: Claude Opus 5.5
skills: guideline-audit
app_version: 1.5.1
commit: 045ccd4
repo: app
---

## Report
[Audit 10](../../reports/2026-10-29-phone-tab-audit/report.md) (owner, 2026-10-29: "the phone is cluttered and not
polished; focus on quick actions and info, not deep analysis"). Each step names its findings (F1...). Add's amount-first
sheet is NF-3AD; Settings' tabs and the cut and small-target faults are IV-3T. Owner decisions D1-D3 change Part C:
build those parts only once the owner has chosen, and change the guideline in both repos in the same session.

**The test for each step:** the first screen holds the tab's one answer, its daily action and the latest money; what
explains, compares or charts is one tap away.

## 3AL1 Overview (F1-F3)
One Needs you strip under the stepper: the "due today or tomorrow" card joins it as its first item; "Manage Needs you"
becomes the last row inside it. Your position as flat rows that open their pages; This period's figures as rows that open
a sheet (D1), never a fold inside a fold.

## 3AL2 Budget (F5-F8)
One category list: over plan, then ahead of pace, then "N on track" as one row that opens the rest. A row opens a sheet
with the limit field, Cover it and See transactions; no inputs in the list. Your plan becomes one line under the hero;
Spending by group leaves the phone page. Show the System group's `note`, not "System Categories". Bulk undo, the raise
offer and first limits take the strip's place one at a time.

## 3AL3 Transactions and an account (F10-F12)
Open on this month (the stepper shows), on Transactions and on an account; All time stays in Choose period. Money in and
out as one line (D2). Views and value updates move into ⋯. A day's net only on a day with two or more rows.

## 3AL4 More (F13-F14)
Flat, three headings (D3): Due soon (rows; a tap opens the pay sheet, no button on each row), Your money (sections with
their figures), the Weekly review card, Settings (names only, no subtitles). When nothing falls before payday, say what
is next ("Next: Landlord 12,000 on 2026-11-03").

## 3AL5 Pages under More (F15-F20)
Cash planning: the next payment when nothing is before payday; forecast, months ahead and What is promised as rows that
open sheets. Recurring: the list first, Add as a Secondary, the fixed-costs ratio a link to Financial health, no ".00".
Reserves: the app bar names Financial health; no card in a card. Investments: holdings right after the hero, the chart
one row; the horizon set on the phone or its row removed. Accounts: Accounts tab first. Financial health: the limit that
needs you leads, with its action; the chart one tap away.

## 3AL6 Spending (F21)
The lead (spent this month against the same days usually), four biggest categories then Other as rows, then one row
"More analysis" that opens the rest. The heat map, both money-flow diagrams, small multiples and month grid leave the
first page.

## 3AL7 Weekly review (F22)
More stays chosen in the tab bar; no lone tab chip; a decision's title is not repeated in its row; no cut "Review"; one
Primary to record the review.

## Fix
`lightning/ui/templates/phone/` and `phone.css` (regenerate `phone.rtl.css`); the default period in
`routes/register.py`; Mohab and `tools/phone_check.py` after each step; re-run the audit's `evidence/capture.py` and
compare the table.
