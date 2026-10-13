# Lightning — Project Overview

**Last reviewed 2026-10-13 · app 1.0.0-beta.1** (v1.1 work is merged to `main` but not yet versioned or released).

What Lightning is, who it is for, what it answers and where it goes. Technical contracts: [Architecture](ARCHITECTURE.md). Look: [guideline](../guideline/). Terms and figures: [Glossary](GLOSSARY.md). Shipped changes: `CHANGELOG.md`. Hand-off between AIs: [NOW.md](../NOW.md). Unbuilt designs: [docs/proposals](proposals/).

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
| 9. Upcoming projects | You pick the next feature |
| 10. Roadmap | You plan or finish a milestone |

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
| **One ledger** | Registers, budget actuals, investments, Overview and reports are views of one transaction ledger. |
| **Other people's money** | *Held for others* stays in the account balance, is left out of *What you own*, and is not income, spending or money owed to you. |
| **Obligations count, forecasts never do** | Bills due and loans still to pay make *What you owe*: bills due come off Free cash, What you owe off Net worth. Loans are schedules, not debt accounts; a payment is spending when paid. Credit cards, loan-interest accounting and money owed to you are out of scope; CD interest is an estimate. |
| **Reserves are not budgets** | A reserve sets aside cash you own and lowers Free cash; a budget limit changes only the plan; never added together. Emergency fund is shown in months of *Average monthly income* (2026-10-05), or of spending if Settings › Budget says so. |
| **Categories describe the activity** | L1 Personal / Work / Investment / System Categories, L2 broad, optional L3. Each is + income, − expense or ±; income is recurring or irregular; an expense can be one-off. A used category is archived, never deleted. |
| **Names are canonical** | Similar spellings are suggestions the user picks. Never silently merge or create a counterparty. |
| **Physical gold** | Per piece: net weight, karat, cost. Valued per gram of the same karat; purity never applied twice. |
| **People see names, not codes** | Summaries in whole pounds, inputs keep cents, ISO dates. Entry accepts `31/1`, Arabic-Indic digits and sums such as `120+35*2`. |
| **Each visual names its time frame** | The chosen period or a fixed horizon (section 4). |
| **Holdings value = Portfolio value** (2026-10-04) | Everything owned that is not cash, deposits included, on every tab and chart. |
| **Every release stays downloadable** (2026-10-03) | Keep at least the three latest, each with its own immutable download and site entry. Never replace or remove an older one without the owner. |
| **Free 7 days, then a reminder, never a lock** (2026-10-04) | Full app from minute one, no card or account. After 7 days it asks for a licence and never blocks or hides data. Price not set. |
| **The website never mentions other apps** (2026-10-05) | No comparison or "vs" pages (guideline B10, B11). |
| **Each app fetches its own prices** (2026-10-05) | At least at each month-end, plus Update prices any time. The daily collector keeps shared price files as a backup; a typed price always wins. |
| **Prices published only where allowed, always cited** (2026-10-05; FX source 2026-10-07) | FX pack: Banque Misr's dated transfer midpoint, labelled a bank rate, not CBE (CBE rejects the collector). Stock and fund prices from TradingView, Yahoo or Mubasher are for source checks only, never published or shipped, until a licence or permission covers them. |
| **Local only** (2026-10-05) | Data stays on the user's computer, never in Git. Encrypted profiles under Documents/Lightning, password of any length; a 12-digit recovery key plus a security question reset it. One thing opens a profile; two change its password, question or key. Architecture › Encryption. |
| **Two levels, few settings** (2026-10-06) | Six sections, at most five tabs each, no third level; settings behind a tab's gear; a default before a setting; icons for row actions; one choice, one field. Architecture › UI contract. |
| **Phone has its own design** (2026-10-06, 2026-10-07) | Part C of the guideline; never the PC layout squeezed. Every icon has its word (alone only if universal); four tabs as two rows of two; add button on every section's first page; the Overview is one screen (Get set up, Needs you, four tiles, Your position). |
| **Fewer steps to set up** (2026-10-06) | Recovery key shown once and confirmed with a press. One password on every device. |
| **Order to Google Play** (2026-10-06) | M1 phone and PC connected; M2 daily recording on the phone; M3 bank SMS into the ledger; then beta and Google Play. The owner reviews at each milestone. |

**Multiple devices (phone as home), planned and partly built.** One codebase on PC and Android; the phone holds the accepted encrypted ledger and one paired PC borrows it. Build status is in the Roadmap. Design, lend safety, hand-back, bank SMS: [multiple_devices.md](proposals/multiple_devices.md). **Edit anywhere, one home confirms** (owner-requested revision 2026-10-07, supersedes automatic lending only after cutover, unscheduled): [edit_journal.md](proposals/edit_journal.md). A server or cloud copy is outside version 1.

<a id="what-you-can-do-today"></a>
## 3. What you can do today

Specs live in [Architecture](ARCHITECTURE.md); terms in the [Glossary](GLOSSARY.md).

- **Accounts and ledger:** accounts with starting balances; money in, out, internal transfers; edit, void, restore, bulk select, search; check an account against the bank's balance (small gaps become one adjustment).
- **CSV import:** one signed or separate in/out columns; one decision per new name; duplicates flagged; waiting reviews can be continued or discarded.
- **Budget:** Planned, Spent, Left in plan; amount or %; carryover; All time, YTD, Monthly, Custom; savings target and goals protected; Fill this month; low-confidence estimates marked.
- **Cash planning:** Safe to spend, What you owe, next 30 days, three-month forecast; Recurring bills, subscriptions and income (suggested, never created on their own); Loans with payoff date; Reserves with the emergency fund.
- **Needs you (Overview):** the one review inbox: statements waiting, uncategorized transactions, bills due, missing prices, plan problems.
- **Financial health:** named figures with profile-owned limits and six completed months of trend. No score.
- **Investments:** buy, sell, dividends; prices fetched, typed or from shared files; Net gain or loss; Holdings after sale; target allocation; certificates and time deposits per certificate; US stocks priced in USD with price and FX parts of the gain (v1.1).
- **Currencies:** foreign cash with dated rates, Convert, per-currency position with realized and unrealized FX gain (v1.1).
- **Held for others** and **cash ownership:** reassign cash between you and a saved person, or record an expense paid for you.
- **Gold:** pieces with weight, karat and cost.
- **Rules:** Settings › Rules file counterparties by condition.
- **Search and type faster:** Ctrl-K, #tags, sums in amount fields, privacy mode (the eye).
- **Arabic and phone:** the whole app in English or Egyptian Arabic, PC and phone; the phone records daily, reads CIB and NBE bank SMS with permission and hands the ledger to a PC over local Wi-Fi.
- **Profiles and release:** encrypted named profiles with recovery key; Windows ZIP (`Lightning.exe`, no Python) and signed Android APK published together from one tested commit (beta, 1.0.0-beta.1). Still open: ordinary-Windows recovery/fault acceptance, legacy import. Use an independent backup.
- **Samples:** `python -m lightning --demo` (Mohab's last three months); an empty profile can load Mohab's year or the stories of Amr, Abdelrahman, Menna or Fatma.

<a id="period-and-fixed-horizon-visuals"></a>
## 4. Period and fixed-horizon visuals

The period picker (All time · YTD · Monthly · Custom) drives most visuals. A few keep a fixed horizon, and each section header says which.

| Follows the period | Fixed horizon |
|---|---|
| Overview: stat cards, Cash flow, Investments section | Overview: Net worth over time (12 month ends); position cards (today) |
| Budget: waffle, plan bar, Spent of plan | Budget: plans are monthly; longer periods add months |
| Investments: waffle, Net gain or loss, allocation and biggest holdings (as of period end), money and value by class | Portfolio value sparkline (last 6 months); Dividends (year to date); XIRR (annualized since first investment, including periods shorter than a year); horizon bar (today) |
| Expense analysis: KPI cards, treemap, now against usual, daily calendar or monthly summaries | "Usual" is the 6 whole months before the period; usual range, small multiples, heatmap use the 12 before it |
| — | Holding page: whole history up to 24 month ends; sparklines last 6 |

A sparkline never follows the period. A comparison always looks at whole months before the period.

<a id="the-questions-lightning-answers"></a>
## 5. The questions Lightning answers

Each tab answers one main question, then its follow-ups. Reviewed 2026-10-13; `tests/test_mohab_year.py` checks the answers, so only open gaps are listed below.

| Screen | Main question | Leads with |
|---|---|---|
| Overview | Where do I stand, and what needs me? | Needs you, Net worth, Free cash, what it is made of, cash flow |
| Expense analysis | Where did my money go? | Money out, ranked categories, change from last period |
| Budget | Am I on plan? | Left in plan, categories over plan |
| Investments | What do I hold, and how did it do? | Net gain or loss, holdings, allocation |
| Cash planning | How much can I actually spend? | Safe to spend, What you owe, forecast |
| Reserves | Am I safe if something goes wrong? | Emergency fund in months |
| Financial health | How do my figures compare with my limits? | Emergency fund, Savings rate, debt and fixed-cost ratios |
| Account | What happened here? | One balance, add/import, register |
| Held for others | Whose money am I holding? | Balances by person |
| Settings · Checks | Is my data right? | Integrity checks |

Every other follow-up (net worth breakdown, what I owe, spend until payday, due next, forecast low point, categories over plan, loans in the plan, class returns, sale value, target mix, payoff date, debt ratios, bonus and job-change effects, fees) is answered. Open gaps:

| Question | Gap |
|---|---|
| Why did net worth change: saving, prices or new money? | Partial: no wealth-change bridge (M3.2) |
| Can I afford this purchase now? | Partial: no "what if I buy it" check |
| A merchant or a few categories I care about | Missing: no saved watchlist |
| A refund: did my spending go down? | Partial: it lowers the category in the month the refund arrives, not the purchase month (Mohab 13) |
| Work spending my employer owes me back | Partial: nothing lists what is unreimbursed |
| What about next month's plan? | Partial: rules repeat; a future month cannot be opened |
| Where should the rest of my income go? | Missing: no "ready to assign" view |
| Have I actually set aside the goal's monthly amount? | Partial: nothing asks him to assign it |
| I paid from the emergency fund: what now? | Partial: nothing reminds him to refill (Mohab 14) |
| Pay the loan off early | Missing: no lump-sum payment |
| When does my certificate mature? | Partial: legacy account-level terms not converted; no bank reconciliation |
| How are my dollar savings and US stocks doing? | Built in v1.1; open: bank-imported pairs across currencies, Europe and GCC listings |
| No pay this month: does the average fall? | Known gap: zero-income months are skipped by the average (Mohab 27) |
| Was I paid my raise? | Partial: the scheduled payment stays Due until linked by hand |
| Is my salary late? | Left out by decision |
| Stale prices | Needs you flags prices older than about two months; month-end price gaps are listed |

Early pay, raise and rent changes need explicit confirmation by design: Lightning suggests, Mohab confirms, neither plan nor reserve changes silently. Left open by the 2026-10-05 audit: a payment scheduled on the 31st moves to the 30th after a shorter month and stays there.

<a id="reference-workflow-a-month-with-mohab"></a>
## 6. Reference workflow: a month with Mohab

**Mohab**, 31, salaried, Cairo: 45,000 EGP a month from ACME Egypt into CIB; a cash wallet and Vodafone Cash; an NBE 3-year certificate; a THNDR account with COMI, Fawry and a money market fund; an L'Azurde ring and a gold pound; 10,000 EGP of his mother's money in CIB; rent, internet, phone, electricity, and a 24-month car loan.

`tests/test_mohab_year.py` (read its docstring) runs steps 1–31 through the screens, one test per step. It judges answers, route from the Overview, effort, speed, simplicity, clarity and UI. When a gap is fixed, change its assertion and the Today column together.

**Steps 1–10, one ordinary month (July–September 2026):** open six accounts (dates as `1/7`); import 40 CIB rows (39 posted, 1 skipped, Mom's 10,000 is Held for others); move money to THNDR and buy COMI, Fawry and a fund; record the ring and the gold pound; cash and Vodafone Cash spending; month-end prices; a 20,000 emergency fund and the budget (Free cash = Cash you own − Reserves − Bills due); track recurring items and the car loan (What you owe 60,000); on 2026-10-06 mark salary, rent and a loan payment paid (Net worth moves only by +45,000; loans still to pay 57,500); read every tab, Checks pass.

**Steps 11–31, October 2026 to September 2027:**

| # | When | Step | Today |
|---|---|---|---|
| 11 | Oct | An ordinary month settles itself | Answered |
| 12 | 10 Oct | ATM withdrawal 2,000 with 25 fee | Answered |
| 13 | 15 Oct | Returns August's 1,299 purchase | Partial: October reads −1,299, August keeps it |
| 14 | 18 Oct | 6,500 repair from the emergency fund | Answered; no refill reminder |
| 15 | 20 Nov | 300 COMI dividend | Answered |
| 16 | Dec | Work Uber 1,200 paid back by ACME | Answered |
| 17 | 20 Dec | 90,000 bonus | Answered; average stays 45,000 |
| 18 | 24 Dec | January's salary arrives early | Answered after he confirms the suggestion |
| 19 | Jan–Apr | 9,000 insurance goal, 2,250 a month | Answered; cash moves only when he assigns it |
| 20 | 1 Feb | Raise to 50,000 | Answered with confirmation |
| 21 | Mar | Eid gifts given and received | Answered |
| 22 | Mar | Phone on 12 installments of 2,000 | Answered (as a loan) |
| 23 | 20 Apr | Sells 75 of 150 COMI for 7,100 | Answered |
| 24 | 3 Jun | Rent rises 10% to 13,200 | Answered with confirmation |
| 25 | Jul–Aug | 15,000 Sahel trip goal, 14,200 spent | Answered |
| 26 | 31 Aug | Leaves ACME (30,000 end of service), Valeo at 55,000 from 1 Oct | Answered |
| 27 | Sep | Between jobs, no pay | Known gap: test checks the average does not rise, not zero-month inclusion |
| 28 | 30 Sep | Reads the year: Money in 651,300, out 295,186, Change in what you own 357,364, loans 34,500 | Answered except *why* (M3.2) |
| 29 | 30 Apr | Safe to spend after raising his target | Answered |
| 30 | May–Jul | 60,000 laptop by 30 June | Answered |
| 31 | 30 Sep | Moves Talabat to Food | Answered |

The dollar steps are not yet inside the year (NOW.md, Next 3). User feedback batch 001 is checked by nine named screen assertions; loading speed, scroll position, compact review rows, chart colours and register balance are judged on a real PC.

**Not scripted:** gam'eya (no type; an inflow needs an income category); the NBE certificate maturing (forecast only; he enters redemption and interest by hand); paying the car loan off early; payslip deductions (record net pay).

<a id="compared-with-the-best-budgeting-apps"></a>
## 7. Compared with the best budgeting apps

Evidence, and what users of the Egyptian apps love and hate, are in [Competition](COMPETITION.md); this is only the gap list, reviewed 2026-10-13. Already on par: suggested (never created) recurring items, bills with paid-matching, projected balance with its lowest point, dated goal needs, yearly subscription totals, loan payoff, rollover budgets, review inbox (2026-10-05), rules with conditions, multi-currency (v1.1), real investment returns, local gold, money held for others.

| # | Still missing | Why it matters |
|---|---|---|
| 1 | Capture on the phone in seconds | Cash spending is forgotten unless logged on the spot. Phone recording and bank SMS are built and in owner review (Roadmap); voice and receipt capture are not. |
| 2 | Automatic transaction feed | No Egyptian aggregator exists; PDF and Excel statements (project #17) are the cheaper route. Every parsed message is reviewed before it posts. |
| 3 | Rule suggestions from what you file | A first import still needs one decision per distinct name. |
| 4 | Reminders | A user who doesn't open the app never sees a due bill. |
| 5 | Spending history ("am I improving?") | Answered by Monarch. |
| 6 | Give every pound a job | YNAB's "Ready to assign". |
| 7 | Watchlists, shared household, receipts | Simplifi, Monarch, Lunch Money. |
| 8 | Guided first setup | Done 2026-10-03 for the Overview ("Get set up", dismissible with Done with setup and reopenable from Settings); import from other apps is project #11. |

Bank sync and bill negotiation are not adopted: local CSV stays the foundation. "Safe to spend" must always say which obligations and income it includes. Certificate projections use an actual/365 estimate, are never posted, and interest from the bank is not yet reconciled against them.

<a id="ux-plan-guideline-36"></a>
## 8. UX plan (guideline 3.6)

From the full UX review of 2026-10-03 (Mohab's year at 1,366 × 768) and the tab-by-tab audit of 2026-10-06. Structure is two levels (2026-10-06).

**The user's route:** Where do I start? → Is my money in? → How much can I spend before payday? → What is due? → Am I on plan? → Where did it go? → How are my investments? → Is my data right? Each tab answers one; Needs you is the to-do list across them.

**Done (2026-10-03 to 2026-10-07):** all ten ranked items, in short: Get set up first run; one decision per imported name; category picker; bulk set category; one name, one number; two-line registers; honest price warnings; Reserves table with Refill; whole-EGP words and numbers; the tab-by-tab fixes. Brand audits since are in the CHANGELOG (guideline 3.28–3.30, v1.1 brand pass).

**Owner decisions (2026-10-03):** Budget's low-confidence estimates count in Left in plan with a "!"; the Overview's Investments section is one row of figures linking to the tab.

**Still open:** import button says "Post ready rows" while undecided rows post as Unaccounted; bulk counterparty edit.

<a id="upcoming-projects"></a>
## 9. Upcoming projects

Ideas added 2026-10-05 unless dated; each names its source app (evidence: [Competition](COMPETITION.md)). The owner picks what enters *Next* in `NOW.md`. A built project moves to section 3 and gets a Glossary name.

| # | Project | Idea from | Status |
|---|---|---|---|
| 18 | **High priority (owner, 2026-10-10): listed shares across US, Europe and GCC.** Keep exchange, identifier and trading currency explicit; value in base currency; check source coverage and licensing first | Owner | US stocks built (v1.1). Open: LSE, Euronext, Xetra, SIX, Nasdaq Nordic and the six GCC markets. [market_data.md](proposals/market_data.md) |
| 1 | Return against the risk-free rate (certificate or T-bill over the same dates); needs a dated rate history and time-weighted return | Quicken, Monarch | Not started |
| 17 | Read PDF and Excel statements through the CSV review (size caps, no macros, no formulas run) | Say, Quicken, Monarch | Not started |
| 15 | Multi-currency and FX | Wallet, Lunch Money, YNAB | Built (v1.1). Open: bank-imported pairs across currencies |
| 16 | US stocks | Monarch, Copilot | Built (v1.1), see 18 |
| 2 | Arabic version | Say, Masarifi | Built in the app, PC and phone (CHANGELOG 2026-10-12/13); Hijri dates not built |
| 3 | Financial health | NetTrack, WalletHub | Built 2026-10-05, no score by design |
| 4 | Undo and redo | Actual Budget | Proposal: [undo.md](proposals/undo.md) |
| 5 | Rules with conditions | Actual Budget | Built 2026-10-06. Open: suggest a rule from what you file; rename rule |
| 6 | Layered import match, locked checked month, merge | Actual Budget | Proposals: [import_matching](proposals/import_matching.md), [month_lock](proposals/month_lock.md), [merge_transactions](proposals/merge_transactions.md) |
| 7 | Weekend-aware schedules | Actual Budget | Built 2026-10-06. Open: public holidays |
| 8 | Fill this month | Actual Budget | Built 2026-10-05 |
| 9 | Entry helpers (sums, Ctrl-K, privacy mode, #tags) | Actual Budget | Built 2026-10-05 |
| 10 | Age of Money, spending calendar, one saved filter | Actual Budget | Not started |
| 11 | Move in from Wallet, Money Manager, Masareef exports | Say reviews | Not started |
| 12 | Deeper investments (splits, lots, reinvested dividends, time-weighted return) | Quicken, GnuCash | Proposals: [investment_*](proposals/), [bonus_shares_and_splits](proposals/bonus_shares_and_splits.md) |
| 13 | Silver, property, vehicles | Qershnat | Not started |
| 14 | Gam'eya and zakat | Qershnat, Masroofy | Waits for the owner (OWNER.md) |

For the code (Actual Budget): one change note per change, joined at release; visual snapshots of key screens; a warning on pushes that touch a migration.

<a id="roadmap"></a>
## 10. Roadmap

Reviewed 2026-10-13. Detail of each build is in the CHANGELOG; claims and next steps in `NOW.md`.

| Milestone | State | Next |
|---|---|---|
| M0–M1 Foundation, cash accounts | Shipped | — |
| B Budget | Shipped | Change one category without the full grid |
| M2 Reports and corrections | Partial | Month close ([month_lock](proposals/month_lock.md)) |
| M3 Manual investments | Shipped | — |
| M3.1 Instrument catalogue | Partial | Coverage and identifier quality |
| M3.2 Wealth history | Partial | Wealth-change bridge; owned-only XIRR |
| M4 Market data and FX | v1.1 built: price files, foreign cash, Convert, FX positions, US stocks | **High priority:** Europe and GCC shares (#18); matching bank-imported pairs across currencies |
| M6 Deposits and gold | Partial | CD portfolios built; next: ordinary-PC acceptance, legacy conversion, statement reconciliation, local gold costs and buyback |
| M7 Planning and imports | Partial | CSV import, Cash planning, linking statement rows built. Next: reminders; PDF and Excel (#17) |
| Search | Partial | Built: pages, actions, records, tags, Ctrl-K. Next: scoped pickers, alias history, ranking |
| Multiple devices | M1 and M2 built, in owner review; M3 (CIB and NBE SMS) built | Owner: more bank samples, Google Play SMS declaration. Open: discovery instead of typing the address, prefetch while typing the password, periodic recovery copies, two-PC fault gate, power-loss evidence. [Plan](proposals/multiple_devices.md#15-implementation-work-packages) |
| Paired apps 1.0.0-beta.1 | Tester beta published | Ordinary-PC recovery/fault acceptance, legacy import, native file pickers, unresolved-evidence repair |
| v1.1 | Merged, not released | Owner bumps to 1.1.0 and builds ([v1_1_presentable.md](proposals/v1_1_presentable.md) §5–6) |
| In-app updates (Windows) | Planned for later | **Update** button: check `Lightning-downloads`, verify signature, helper swaps folders, keeps the old for rollback; profiles untouched; refuse during an unfinished lend. Android updates come from Google Play. |

**Next up:** reminders.
