---
title: One page skeleton on the PC, kept by a test - every tab has the same title rule, an answer sentence, its dates, and the same controls in the same order
type: polish
pillar: feel
size: L
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: guideline-audit, bug-hunt
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r35 F5 and F8 ([report](../12-desktop-ux/r35-ux-against-users-questions/report.md), [every tab's title and sentence](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/headers.json)). Owner decision 2026-11-09: **one skeleton, enforced by a test**. Sample year at 1366 × 768:

- **Answer sentence (A05, A09):** 13 of 24 tabs have none: Reports, Recurring, Loans, Reserves, Planner, Prices, Transactions, Import, Held for others, Zakat (dates only), Your data, Rules, Categories (a label). Currencies has one technical sentence of 24 words.
- **Title:** the section's name on Recurring, Loans (Cash planning), Reserves (Safety), Categories, Counterparties, Data checks (Settings); the tab's name on Planner, Investment prices, Currencies, Compare periods, Reports, Rules, Import statements, Accounts, Held for others, Zakat, Financial health.
- **Undo:** in the header row on Overview, Budget, Cash planning; on a second row on Spending, Investments, Transactions, Settings, Limits.
- **Period bar:** in the header (Overview, Budget), on a second row (Spending, Investments, Limits), its own design on Currencies (All time, YTD, Month, Custom), and a fourth copy inside Settings › Ask an AI.
- **Default period:** Spending opens on the last month with a "2026-10 so far · See it" strip; every other tab opens on this month.
- **Primary action:** Transactions' filled button is "Choose an account". Ask an AI lives in Settings › Your data and again as a loose paragraph on Budget.

Screens: [Overview](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/overview.webp), [Spending](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/birdview_expenses.webp), [Investments](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/investments.webp), [Transactions](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/transactions.webp), [Settings](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/settings.webp), [Currencies](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/sheet-planner-prices-currencies-zakat.webp).

## Fix

One header partial renders every tab: the title, the answer sentence, the dates line, the seam; then one control row in one order (tabs, period bar, Undo, gear, more, the one filled action). A page states what it has; the partial decides where it goes. A test walks `sections.SECTIONS` and fails a tab that differs. The guideline changes first where it is silent (title rule, control order): both repos, same session (AGENTS §1).

## How to work on this item

Steps in order; each is one PR. `python tools/guideline.py A05` and `A09` print the rules. After each step: `python -m pytest -q tests/test_brand_audit.py tests/test_mohab_year.py`, and check A16 on the changed tabs. Stay out of `lightning/ui/journal*` (claimed). Delete the step's heading in the same commit.

## 12Y1 Owner: the title rule and the control order · owner
Two choices the guideline does not state, asked as pick-lists: is a tab's title the tab's name (recommended: the sidebar already shows the section) or the section's; and does Spending keep opening on the last complete month (recommended: yes, and its sentence says so) or on this month like the rest. Record the answers in the guideline (A05) and `ai/PROJECT_OVERVIEW.md`.

## 12Y2 The test first, with today's exceptions listed · M · opus
File: a new `tests/test_page_skeleton.py` using the browser fixture of `tests/test_brand_audit.py`. For every tab in `sections.SECTIONS` on the sample year: one H1 equal to the rule of 12Y1; a non-empty answer sentence of at most 16 words that does not repeat the title; the control row's order; one filled button at most. Today's failures go in an explicit allow-list in the test, each with this item's code, so every later step removes names from it. Done when the test passes with the list and fails if a listed tab is removed from it unfixed.

## 12Y3 One header partial, used by every tab · L · opus
Files: `lightning/ui/templates/partials/` (the page header), `lightning/ui/static/style.css` (then rebuild `style.rtl.css`), each section's templates. Titles follow 12Y1; Undo, the period bar, the gear and the filled action sit in one order on one row (two rows only when the width needs it, always the same two). Currencies uses the standard period bar. Done when the allow-list has no title, Undo or period entries.

## 12Y4 An answer sentence on the 13 tabs that have none · M · sonnet
Files: `lightning/ui/status.py` (the sentences live in Python, not templates), the tab routes. One plain sentence each, from figures the page already has: Recurring ("Your bills take 14,610 a month, 38% of your income."), Loans ("52,500 left on 2 loans; the last ends 2027-12."), Reserves ("Your emergency fund covers 0.5 months; your limit is 3."), Transactions ("309 transactions; 3 wait to be sorted."), and so on; Arabic for each (`arabic-check`). Done when the allow-list has no sentence entries and Mohab's steps read the new sentences where they assert a header.

## 12Y5 One filled action a tab, and one home for Ask an AI · M · sonnet
Transactions' filled button is Add transaction (Choose an account becomes a quiet control). Ask an AI gets one home (a tab's "more" menu opens it with that tab's period; Settings links to it) instead of a form in Your data and a paragraph on Budget. Done when the skeleton test finds one filled button on Transactions and no Ask an AI form inside Settings › Your data.
