---
title: Answer first - rebuild every tab in the guideline 3.33 order (header, Lead, Needs you, KPIs, details)
type: polish
area: product
status: building
created: 2026-10-21
by: Claude
skills: guideline-audit, number-audit, arabic-check
app_version: 1.3.0
repo: both
---

## Why

The owner liked a redesign study of the six tabs (2026-10-21) for its calm, polished look, and asked to keep its essence,
not its screens, and to make sure every tab still answers its questions. The essence became guideline 3.33 (A02.3, A05,
A07, A09, A11, A16, C04, C06, C11). This item rebuilds the app to match it, tab by tab, and finishes 3Q steps 3-5 on the way
(each tab step below also does what 3Q §3 lists for that tab).

Owner decisions, 2026-10-21: phone tabs stay icons only; one period control (A05); KPI cards keep A08's five slots; phone
KPI tiles stay 2 × 2 (two in a row when the Lead already answers).

Kept out of the study on purpose: its figures (fake, several wrong), its three-look controls, names under phone tab icons,
the sideways tile strip, Needs you inside the hero, and "Weekly review" renamed (the Overview link opens the review flow,
so the name is right).

## The rules in short (read A09 for the whole)

1. Header: title, status sentence (from the figures, Python), dates, the seam.
2. Lead: the page's answer in one card spanning the row, its working beside it, the watermark.
3. Needs you: this page's items as rows (mark bullet, a few words, where, one action); Overview gathers all of them.
4. KPIs: two to four, A08, each opening its home page.
5. Details: what needs you first, then by size; five columns at most; leave out what says nothing.
6. One home per figure: elsewhere a KPI or a row that links there.

## Steps

### 3W1 Shared parts

`page_header` gains the status sentence and the seam; a `lead_card` macro (figure, comparison, working rows or chart, the
watermark); a `needs_rows` macro fed per page from `review.grouped` filtered by page; sidebar chosen item gets the seam.
Status sentences live in one Python module (`lightning/ui/status.py`), one function per page, built from the figures the
page already has; English and Arabic (`i18n`). CSS: one block, old layers deleted as each page moves.

### 3W2 Overview

Lead: Net worth with What you own and What you owe, the line over time beside it. Needs you: every page's items, with the
count. KPIs: Savings rate, Investing rate, Safe to spend, Money out (3Q §3). Then one row of link cards to each home: Free
cash (Cash planning), What it is made of (Investments), Net flow (Budget or Spending). If you sold today moves to
Investments; the two money-flow diagrams and Month by month move to Spending.

### 3W3 Budget

Lead: Left in plan with its segmented bar and the daily amount; Is everyday spending on pace? beside it. Needs you: each
category over plan with Move from (`budget_move.html`). Spent of plan: one list, over plan first, then by size. Bills in
this month's plan stays. Spending by group goes; Plan leaves to save moves to Financial health (Planned savings rate).
The settings gear joins the control row.

### 3W4 Cash planning

Lead: Safe to spend with Free cash down to Safe to spend beside it. Needs you: late bills. Then The next 30 days with Mark
paid, and Free cash then the forecast. The dot timeline that repeats the list goes; What you owe lives on Loans.

### 3W5 Investments

Lead: Portfolio value, Net gain or loss and its return in the comparison, Cost and Unrealized gain as working; the split by
asset class as one bar beside it with the trend. Holdings table: five columns (Holding, Cost, Value, Unrealized gain, Since
purchase), account and class under the name. By currency only when something is not in EGP, else one line. The waffle and
Biggest holdings go. If you sold today (estimate) arrives here as a row with its own words.

### 3W6 Accounts

Lead: What you own, with In your accounts and Held for others beside it so the difference is explained. The table becomes
groups (Cash and bank, Deposits, Investments, Physical items) with a total each; two money columns; balances are figures,
not links (the row opens the account); Transactions count goes.

### 3W7 Financial health

Lead: Within your limits ("5 of 6"), the savings rate over time beside it. Needs you: the one outside its limit, with its
action. Against your limits: one row each (bar, figure, verdict). The four top cards that repeat the list go; Net worth over
time lives on Overview.

### 3W8 Phone, Arabic, acceptance

Each page in the C04/C06/C11 order; `tools/phone_check.py` at 360 and 320; arabic-check; Mohab (`tests/test_mohab_year.py`)
and number-audit after every step that moves a figure; site-recapture once Overview, Budget, Investments and Cash planning
are done.
