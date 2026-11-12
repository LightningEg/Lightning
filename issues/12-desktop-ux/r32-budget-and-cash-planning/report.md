# Audit 18: Budget and Cash planning, every tab and sub-page

Date: 2026-11-09 · Author/reviewer: Claude
Repository: app · Reviewed commit: 90f01900587841fa8fdea859fbf9f2cc8314140a
Code: r32 · App version: 2.1.2

## Assessment

The two front pages are strong: Budget answers "am I on plan?" with a pace chart, Cash planning answers "how much can I
spend?" and shows how the figure is worked out. The trouble is behind and beside them. One figure on the phone is
wrong (N1). The same name carries different numbers between the PC, the phone and Home (N2-N5). And the owner's
impression is right: seven sub-pages have no visual and little styling, and two of them light no place in the sidebar.

Order: fix the wrong figure (N1); settle the names (N2-N5); redesign the payday page (U1); then the other bare pages
and the two chosen features.

## Scope and method

Every page of the Budget and Cash planning sections and what they link to: `/budget`, `/budget/fill`, `/budget/raise`,
`/budget/move`, `/budget/carryover-bridge`, a category's sheet and Change limit, Budget settings, `/payday`, `/plan`,
`/plan/recurring`, `/plan/loans`, `/plan/scenarios`, `/plan/inputs`, the new recurring item and instalment forms.
Sample household on throwaway encrypted profiles, date 2026-11-09, PC at 1366 x 768 and the phone app at 390 x 800.
Each page was captured and measured (cards, charts, tables, inputs, overflow: [metrics](evidence/metrics.json)), then
read by eye; figures were compared across pages. Scripts: [flows/](evidence/flows/) (`python host.py hosts.json`,
Chromium on debug ports 9333 and 9334, `node login.js`, then `b1.js`, `b2.js`, `b3.js`).

## Findings

Severity: high = a wrong figure; medium = a contradiction or an unfinished page; low = polish.

### Figures

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| N1 | high | Phone Budget, *Where the month went*: 33,851 Spent. The month's spending is 19,001; the donut adds fixed costs paid (14,850) on top of the categories that already hold them. [Screenshot](evidence/phone-budget.png). | BV-12O |
| N2 | medium | *Left in plan* is 6,598 on the PC and on Home, 5,468 on the phone Budget (the everyday part). | IV-12P fixed; [one name, one figure](../../../tests/test_one_name_one_figure.py) |
| N3 | medium | Home: "Safe to spend 51,420 · About 249 a day until payday". 249 a day belongs to the budget's 5,468, not to 51,420. Two answers to "how much can I spend?" in one line. | IV-12P fixed; [one name, one figure](../../../tests/test_one_name_one_figure.py) |
| N4 | medium | "Lowest point ahead 51,420" (Plan) against "Lowest scheduled cash 86,288" (Scenarios) for the same months. | IV-12P fixed; [one name, one figure](../../../tests/test_one_name_one_figure.py) |
| N5 | low | "Plan leaves to save 19,401" and "Not yet given a job 13,997" two rows apart; the lead figure of Cash planning differs between PC (Safe to spend) and phone (Due before payday). | IV-12P fixed; [one name, one figure](../../../tests/test_one_name_one_figure.py) |

### Unfinished pages

| ID | Severity | Page | Observation | Follow-up |
| --- | --- | --- | --- | --- |
| U1 | medium | Fund your payday plan | No visual, jargon lines, ten stacked boxes with piastres; proposes 60,420 of 67,018 free cash for the emergency fund, 0 left unassigned. [PC](evidence/pc-payday.png), [phone](evidence/phone-payday.png). | IV-12Q1 done: `tests/test_payday_proposal_adds_up.py` |
| U2 | medium | Compare scenarios | A form and a two-row table, no chart; no sidebar item or tab is lit. [Screenshot](evidence/pc-scenarios-and-forecast-inputs.png). | IV-12Q2 done: `tests/test_budget_cash_page_pattern.py` |
| U3 | medium | Forecast inputs | No title, six bullets each ending "Review inputs", nothing lit in the sidebar. | IV-12Q2 done: `tests/test_budget_cash_page_pattern.py` |
| U4 | medium | Change limit | One box, "Amount or %", on an empty page; nothing about what was spent. [Screenshot](evidence/pc-change-limit.png). | IV-12Q3 done: `tests/test_budget_cash_page_pattern.py` |
| U5 | low | Fill this month, Carryover | Empty table, "No base limits from last month are available to copy"; *Give it a job* (13,997) leads here and stops. [Screenshot](evidence/pc-carryover-and-fill.png). | IV-12Q3 done: `tests/test_budget_cash_page_pattern.py`, NF-12R |
| U6 | medium | Phone Recurring | A plain list and text rows: no card, no bar. On the PC the bills are listed twice. [Screenshot](evidence/phone-recurring.png). | IV-12Q4 done: `tests/test_budget_cash_page_pattern.py` |
| U7 | low | Phone Cash planning | "Compare scenarios" and "Forecast inputs" are bare underlined links above the content. [Screenshot](evidence/phone-cash-planning.png). | IV-12Q2 done: `tests/test_budget_cash_page_pattern.py` |
| U8 | low | Budget, Budget settings | The Ask-an-AI paragraph and the "Not yet given a job" rows sit bare between cards; settings is 38 checkboxes including "System Categories". [Budget](evidence/pc-budget.png), [settings](evidence/pc-budget-settings.png). | IV-12Q5 done: `tests/test_budget_cash_page_pattern.py` |

### Smaller things

- The next-30-days list on Cash planning puts the gam'eya instalment (12-05) after a 12-09 row, and its name is not underlined like the others.
- Amounts with ".00" on Recurring and in Change limit (A16: whole EGP).

### What works

- Budget: the pace chart against last month, "about 249 a day", spent-of-plan bars, untouched categories folded away,
  a category's sheet ("Ahead of pace: 70% spent, 30% of the month gone").
- Cash planning: Safe to spend with its worked-out bars, *Can I afford this?* ("Yes. You keep 21,420 safe to spend
  until 2026-12-01."), the next 30 days with *Mark paid*, the forecast and in-and-out charts.
- Recurring (PC): fixed costs to income against a limit, *Looks recurring* suggestions. Loans: paid-off date, ratios, *Pay early*.

### Features considered

| ID | Feature | Owner, 2026-11-09 | Follow-up |
| --- | --- | --- | --- |
| F1 | Fill this month from the average of the last three months | Built (NF-12R) | `tests/test_budget_fill.py::test_average_source_uses_three_full_months_and_one_month_of_history` |
| F2 | Warn before a category runs out, with Move room or Raise | Built (NF-12S) | `tests/test_running_out.py` |
| F3 | Bills on a calendar | Not chosen | none |
| F4 | Change limit shows the last three months | Not chosen (the popup of IV-12Q3 shows this month only) | none |

## Validation and limits

Browser evidence on sample data; the full suite was not run because no code changed. Not checked: saving a limit,
applying a fill, marking a bill paid, adding a recurring item or loan, turning cash funding on, carryover with real
history, Arabic, themes, the Android app itself. Safety (Reserves, Limits) was captured but not audited.

## Dated follow-ups

- **2026-11-09, owner decisions (question dialog).** Payday page: redesign as one short step (IV-12Q1). Features: F1
  and F2 go in the plan; F3 and F4 were offered and not chosen.

- **2026-11-09, owner decisions, second round (question dialog).** Home leads with the everyday budget; Safe to spend
  stays the lead of Cash planning (IV-12P).

- **2026-11-12, IV-12Q finished (Claude).** All five steps built: the payday page is one short step and tops reserves
  up by their monthly need (`tests/test_payday_proposal_adds_up.py`); scenarios, forecast inputs, change limit, fill,
  carryover, recurring, Budget and Budget settings follow the page pattern (`tests/test_budget_cash_page_pattern.py`).
