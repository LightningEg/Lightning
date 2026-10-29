---
title: Phone declutter, tab by tab - each tab opens on its answer and its daily action; analysis one tap away
type: polish
area: phone
status: building
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
sheet is NF-3AD; Settings' tabs and the cut and small-target faults are IV-3T. The owner left D1-D3 to Claude
(2026-10-29): D1 sheets, D2 chips plus a one-line money strip, D3 flat (built). D1 and D2 change Part C (C06.2, C08.1,
C08.3, C11.1): change the guideline in both repos in the same session, then build them.

**The test for each step:** the first screen holds the tab's one answer, its daily action and the latest money; what
explains, compares or charts is one tap away.

**Built 2026-10-29** (tests in `tests/test_phone_frame.py`, `test_phone_budget.py`, `test_phone_transactions.py`): one
Needs you strip; Budget lists each category once and edits behind Edit plan; Transactions opens on this month; More is
flat; the weekly review keeps More chosen, and 3AL7 is done. Then: Cash planning names the next payment after payday;
Recurring's page action is a Secondary; Investments' horizon note points to the holding; Financial health puts what
needs you under its lead with the chart in its own card. Each step below says only what is left.

## 3AL1 Overview (F1-F3)
Left: Your position as flat rows that open their pages; This period's figures as rows that open a sheet (D1), never a
fold inside a fold.

## 3AL2 Budget (F5-F8)
Left: a category row opens a sheet with its limit field, Cover it and See transactions (today the row opens its
transactions and limits are typed under Edit plan). Bulk undo, the raise offer and first limits take the strip's place
one at a time.

## 3AL3 Transactions and an account (F10-F12)
Left: Money in and out as one line (D2). Views and value updates move into ⋯. A day's net only on a day with two or
more rows. (Built: the tab opens on this month; an account's page stays its statement, all time with the balance after.)

## 3AL4 More (F13-F14)
Built, flat with headings (the guideline's way of D3). Done.

## 3AL5 Pages under More (F15-F20)
Left: Cash planning's forecast, months ahead and What is promised as rows that open sheets (D1). Recurring: the
list first, the fixed-costs ratio a link to Financial health, no ".00" on rows. Reserves: the app bar names Financial
health; no card in a card. Accounts: Accounts tab first (the section registry is shared with the PC: ask first).
Investments keeps the owner's PDF order (chart, then holdings).

## 3AL6 Spending (F21)
The lead (spent this month against the same days usually), four biggest categories then Other as rows, then one row
"More analysis" that opens the rest. The heat map, both money-flow diagrams, small multiples and month grid leave the
first page.

## Fix
`lightning/ui/templates/phone/` and `phone.css` (regenerate `phone.rtl.css`); the default period in
`routes/register.py`; Mohab and `tools/phone_check.py` after each step; re-run the audit's `evidence/capture.py` and
compare the table.
