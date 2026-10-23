# Lightning — Project Overview

**Last reviewed 2026-10-23 · source 1.4.3 · latest published beta 1.4.2** ([published Windows and Android beta](https://github.com/LightningEg/Lightning-downloads/releases/tag/v1.4.2)).

What Lightning is, who it is for, what it answers and where it goes. Technical contracts: [Architecture](ARCHITECTURE.md). Look: [guideline](../guideline/). Terms and figures: [Glossary](GLOSSARY.md). Shipped changes: `CHANGELOG.md`. Hand-off between AIs: [NOW.md](../NOW.md). The plan and open items: [issues/](../issues/INDEX.md).

## Contents

Read one section: `grep -n '^## ' docs/PROJECT_OVERVIEW.md`, then read from that line.

| Section | Read it when |
|---|---|
| 1. What Lightning is | You are new to the product |
| 2. Product decisions that must hold | You change any figure, rule or flow |
| 3. What you can do today | You need the feature list |
| 4. Period and fixed-horizon visuals | You change a chart, card or the period picker |
| 5. The questions Lightning answers | You change what a screen answers, or take a known gap |
| 6. Reference workflow: a month with Mohab | You change Mohab's test or a screen he uses |
| 7. Compared with the best budgeting apps | You plan a feature |
| 8. UX plan (guideline 3.6) | You take a UX item |
| 9. Plan and roadmap | You pick the next work or finish a milestone |

<a id="what-lightning-is"></a>
## 1. What Lightning is

A local-first personal wealth app for Egyptians. It shows where money is held, what it is invested in, how spending compares with the plan, and how what you own changes. The loop: record or import activity, sort out unclear names and categories, read the analysis, save towards goals.

Two questions stay apart: **where** value is held (an account such as CIB, the cash wallet, gold at home) and **what** is held (EGP cash, COMI shares, fund units, gold grams, deposits, dollars).

Every number comes from one of three layers, and each screen says which:

- **Ledger:** real money. Posted transactions.
- **Plan:** what-if. Budgets, reserves, scheduled bills and loans, sale factors, the forecast. Moves no money.
- **Report:** reads both. The Overview and the reports under it store nothing.

**For whom:** a busy user who won't read help text. One name and one calculation per figure; a name that needs explaining gets renamed. Every action shows feedback. A wrong or silent result is worse than an extra click. **Priorities:** fewest clicks, same words everywhere, durable searchable data, broad coverage of normal cases. Calculations, matching, prices and categorization are ordinary code, never AI calls.

<a id="product-decisions-that-must-hold"></a>
## 2. Product decisions that must hold

Dates are when the owner decided. Undated rows are founding rules.

| Decision | Rule |
|---|---|
| **Branches** (2026-10-12) | Work on `who/feature`, merge finished work into `main`. [AGENTS.md](../AGENTS.md) section 6. |
| **Arabic is for Egypt** | English and Egyptian Arabic for the same profile; the website links matching pages. Arabic reads right to left; money, dates, codes and identifiers keep their natural order. Names: [Glossary](GLOSSARY.md#العربية--المسرد-العربي). |
| **Feedback screenshots stay private** | Up to five images per ticket, stored in the Apps Script owner's private Drive folder, linked in the feedback Sheet. The website repo owns it. |
| **Savings and reserve matching** (2026-10-19) | The waffle shows savings only, including savings allocated to investments, with positive Overspent figures and darker spending squares when spending exceeds income. Reserve matching can combine account, counterparty and category; all selected criteria must match. |
| **KPI cards compare** (2026-10-19) | Every KPI card shows a comparison (guideline 3.32, A08): five fixed slots, no icon tile; two to four cards fill a row; a key note never forms a row of its own. Budget's day rate counts only everyday money, not bills still to pay in the plan. The savings waffle lives only behind the Overview's Savings rate. Price and net-worth charts keep their axis from zero and name the change. [3Q](../issues/3-polish-and-arabic/3Q-visual-audit-cards-that-compare.md) builds it. |
| **Answer first** (2026-10-21) | Every page opens on its answer: header with a status sentence and the dates, the Lead with its working, Needs you, KPIs, then details; one home per figure (guideline 3.33, A09). KPI tiles 2 × 2 on the phone. Built (3W). Where money in went (beside the last six months, ticket 78) and Month by month (tickets 79, 86) moved from the Overview to Spending (owner, 2026-10-21). |
