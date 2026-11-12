---
title: The unfinished pages of Budget and Cash planning get the page pattern: a lead figure, a visual, cards
type: polish
pillar: plan
size: L
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: bug-hunt, guideline-audit
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r32](r32-budget-and-cash-planning/report.md) U1-U8 (owner, 2026-11-09: "some tabs are unstylised with no visuals"). Measured on every page:
[metrics](r32-budget-and-cash-planning/evidence/metrics.json). Each step follows guideline A (PC) and C (phone): `python tools/guideline.py`.

## 12Q1 Fund your payday plan, as one short step · M
Owner decision 2026-11-09: redesign as one short step. Today: [PC](r32-budget-and-cash-planning/evidence/pc-payday.png), [phone](r32-budget-and-cash-planning/evidence/phone-payday.png).
No visual; lines such as "Owned cash 87,018 · Reserves 20,000 · Funded spending left 0 · Unfunded bills due 0"; ten
full-width boxes with piastres; and the proposal sends everything not needed for everyday (60,420 of 67,018) to the
emergency fund, leaving 0 unassigned, while the page says Safe to spend stays 51,420. New page: three bars (bills
before payday, everyday, savings and goals) that add up to the cash, one Confirm, the per-category boxes behind
*Customize*; the proposal tops reserves up to their monthly target, not with all free cash.
**Done when:** the answer and Confirm are on the first screen at 1366 x 768 and on the phone; whole EGP.

## 12Q2 Compare scenarios and Forecast inputs · M
[Screenshot](r32-budget-and-cash-planning/evidence/pc-scenarios-and-forecast-inputs.png). Neither is in the sections registry (`lightning/ui/sections.py`
matches `=/plan` exactly), so no sidebar item or tab is lit; Forecast inputs has no title. Scenarios is a form and a
two-row table: draw the baseline and the scenario as two lines on the plan's forecast chart, with the lowest point
marked. Forecast inputs repeats "Review inputs" on six bullets: group by account, one action each. On the phone both
are bare underlined links above "Coming up": make them rows at the page's end.

## 12Q3 Change limit, Fill this month, Carryover · M
[Change limit](r32-budget-and-cash-planning/evidence/pc-change-limit.png) is one box ("Amount or %") on an empty page; [Fill and Carryover](r32-budget-and-cash-planning/evidence/pc-carryover-and-fill.png)
show an empty table and "No base limits from last month are available to copy". Change limit becomes a popup on the
row (spent this month, a small bar); Fill and Carryover get an empty state that says what to do next. *Give it a job*
(13,997 not yet given a job) must not land on an empty Fill page.

## 12Q4 Phone Recurring and the PC's doubled list · S
[Phone Recurring](r32-budget-and-cash-planning/evidence/phone-recurring.png) is a plain list with no card or visual, then "Every month" as text rows; the
PC shows the same bills twice (a bar list, then the items). One list per device, each row with its share bar; amounts
whole ("12,000", not "12,000.00").

## 12Q5 Budget page and Budget settings · M
On [Budget](r32-budget-and-cash-planning/evidence/pc-budget.png) the Ask-an-AI paragraph with *Copy prompt* and *Edit prompt*, and the "Not yet given a
job" rows, sit bare between cards in the middle of the page: the prompt moves behind the page's menu, the row into the
hero. [Budget settings](r32-budget-and-cash-planning/evidence/pc-budget-settings.png) is 38 checkboxes including "System Categories": group them, say what
ticking does in one line, and drop system categories from the list.
