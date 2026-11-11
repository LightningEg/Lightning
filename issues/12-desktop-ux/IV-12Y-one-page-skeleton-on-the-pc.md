---
title: One page skeleton on the PC, kept by a test - every tab has the same title rule, an answer sentence, its dates, and the same controls in the same order
type: polish
pillar: feel
size: L
model: opus
status: parked
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

## Decided and built

Owner, 2026-11-10 (12Y1): a tab's title is the tab's own name (a section's first tab may carry the section's name: Overview, Cash planning, Investments); Spending opens on this month like every other tab. Both are in guideline A05. Built: `tests/test_page_skeleton.py` (12Y2) with its `ALLOWED` list; the titles of Recurring, Loans, Reserves, Limits, Prices, Import, Your data, Categories, Counterparties and Data checks; Spending's early-month "so far" strip is gone. 12Y4: a status sentence on every tab (`lightning/ui/status.py`: recurring, loans, reserves, held_for_others, currencies; counts elsewhere). 12Y5: Currencies has one filled button; Ask an AI has one page, `/settings/ask-ai`, linked from Your data, Spending and Budget (Budget's paragraph itself goes with IV-12Q5).

## How to work on this item

Steps in order; each is one PR. `python tools/guideline.py A05` and `A09` print the rules. After each step: `python -m pytest -q tests/test_brand_audit.py tests/test_mohab_year.py`, and check A16 on the changed tabs. Stay out of `lightning/ui/journal*` (claimed). Delete the step's heading in the same commit.

## 12Y3 One header partial, used by every tab · L · opus
Files: `lightning/ui/templates/partials/` (the page header), `lightning/ui/static/style.css` (then rebuild `style.rtl.css`), each section's templates. Titles follow 12Y1; Undo, the period bar, the gear and the filled action sit in one order on one row (two rows only when the width needs it, always the same two). Currencies uses the standard period bar. Done when the skeleton test's `ALLOWED` has no Undo or period entries and Currencies uses the standard period bar.
