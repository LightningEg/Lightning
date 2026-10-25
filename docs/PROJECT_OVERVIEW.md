# Lightning — Project Overview

**Last reviewed 2026-10-23 · source 1.4.4 · latest published beta 1.4.2** ([published Windows and Android beta](https://github.com/LightningEg/Lightning-downloads/releases/tag/v1.4.2)).

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
| Cosmetic marketplace owner revision (2026-10-24) | You change cosmetic parts, purchasing or ownership |

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
| **Local pairing** (2026-10-23) | Automatically discover named nearby homes while pairing is open. The joining device selects the number displayed on the home from three distinct choices, then enters the profile password; the home confirms the named device. No QR or typed address. Saved identities reconnect automatically. Recovery keys stay unchanged. |
| **Branches** (2026-10-12) | Work on `who/feature`, merge finished work into `main`. [AGENTS.md](../AGENTS.md) section 6. |
| **Arabic is for Egypt** | English and Egyptian Arabic for the same profile; the website links matching pages. Arabic reads right to left; money, dates, codes and identifiers keep their natural order. Names: [Glossary](GLOSSARY.md#العربية--المسرد-العربي). |
| **Feedback screenshots stay private** | Up to five images per ticket, stored in the Apps Script owner's private Drive folder, linked in the feedback Sheet. The website repo owns it. |
| **Savings and reserve matching** (2026-10-19) | The waffle shows savings only, including savings allocated to investments, with positive Overspent figures and darker spending squares when spending exceeds income. Reserve matching can combine account, counterparty and category; all selected criteria must match. |
| **KPI cards compare** (2026-10-19) | Every KPI card shows a comparison (guideline 3.32, A08): five fixed slots, no icon tile; two to four cards fill a row; a key note never forms a row of its own. Budget's day rate counts only everyday money, not bills still to pay in the plan. The savings waffle lives only behind the Overview's Savings rate. Price and net-worth charts keep their axis from zero and name the change. [3Q](../issues/3-polish-and-arabic/3Q-visual-audit-cards-that-compare.md) builds it. |
| **Answer first** (2026-10-21) | Every page opens on its answer: header with a status sentence and the dates, the Lead with its working, Needs you, KPIs, then details; one home per figure (guideline 3.33, A09). KPI tiles 2 × 2 on the phone. Built (3W). Where money in went (beside the last six months, ticket 78) and Month by month (tickets 79, 86) moved from the Overview to Spending (owner, 2026-10-21). |
| **Arabic body face** (2026-10-19) | Arabic body text is Noto Sans Arabic, more readable than IBM Plex Sans Arabic, which is gone; Readex Pro stays for titles and figures (A06.2). |
| **One ledger** | Registers, budget actuals, investments, Overview and reports are views of one transaction ledger. |
| **Other people's money** | *Held for others* stays in the account balance, is left out of *What you own*, and is not income, spending or money owed to you. |
| **Obligations count, forecasts never do** | Bills due and loans still to pay make *What you owe*: bills due come off Free cash, What you owe off Net worth. Loans are schedules, not debt accounts; a payment is spending when paid. Credit cards, loan-interest accounting and money owed to you are out of scope; CD interest is an estimate. |
| **Reserves are not budgets** | A reserve sets aside cash you own and lowers Free cash; a budget limit changes only the plan; never added together. Emergency fund defaults to months of spending (owner, 2026-10-14); income remains an explicit Settings › Budget choice. Saved choices are preserved. |
| **Categories describe the activity** | L1 Personal / Work / Investment / System Categories, L2 broad, optional L3. Each is + income, − expense or ±; income is recurring or irregular; an expense can be one-off. A used category is archived, never deleted. |
| **Names are canonical** | Similar spellings are suggestions the user picks. Never silently merge or create a counterparty. |
| **Physical gold** | Per piece: net weight, karat, cost. Valued per gram of the same karat; purity never applied twice. |
| **People see names, not codes** | Summaries in whole pounds, inputs keep cents, ISO dates. Entry accepts `31/1`, Arabic-Indic digits and sums such as `120+35*2`. |
| **Each visual names its time frame** | The chosen period or a fixed horizon (section 4). |
| **Holdings value = Portfolio value** (2026-10-04) | Everything owned that is not cash, deposits included, on every tab and chart. |
| **Every release stays downloadable** (2026-10-03) | Keep at least the three latest, each with its own immutable download and site entry. Never replace or remove an older one without the owner. |
| **Free to use; optional cosmetic support** (owner, 2026-10-24) | Every app feature stays free indefinitely: no trial, licence fee, subscription or functional paywall. Optional in-app cosmetics, starting with themes, may be bought to support development; they change appearance only. The purchase and claim flow is still being completed. |
| **The website never mentions other apps** (2026-10-05; again 2026-10-21) | No comparison or "vs" pages or tables, not even against a spreadsheet (guideline B10, B11). |
| **Testing tab for testers only** (2026-10-21, left to Claude) | On lightningeg.com the Testing tab shows after `?testing`; the consent bar is a slim bottom strip. |
| **Found as the all-in-one tracker** (2026-10-20) | The website answers "net worth, budget and expense tracker" with one page, English and Arabic, where every figure is Mohab's and no other app is named. Evidence and follow-up: [Competition](COMPETITION.md), issue 8C. |
| **Each app fetches its own prices** (2026-10-05) | At least at each month-end, plus Update prices any time. The daily collector keeps shared price files as a backup; a typed price always wins. |
| **Prices published only where allowed, always cited** (2026-10-05; FX source 2026-10-07) | FX pack: Banque Misr's dated transfer midpoint, labelled a bank rate, not CBE (CBE rejects the collector). Stock and fund prices from TradingView, Yahoo or Mubasher are for source checks only, never published or shipped, until a licence or permission covers them. |
| **Local only** (2026-10-05) | Data stays on the user's computer, never in Git. Encrypted profiles under Documents/Lightning, password of any length; a 12-digit recovery key plus a security question reset it. One thing opens a profile; two change its password, question or key. Architecture › Encryption. |
| **Two levels, few settings** (2026-10-06) | Six sections, at most five tabs each, no third level; settings behind a tab's gear; a default before a setting; icons for row actions; one choice, one field. Architecture › UI contract. |
| **Locked certificates** (2026-10-14) | Show the owned value and unlock date separately beside If you sold today; do not count it as saleable cash. |
| **Phone has its own design** (2026-10-06, 2026-10-07) | Part C of the guideline; never the PC layout squeezed. Every icon has its word (alone only if universal). The tab bar, Add and the Overview's order: Phone overhaul below. |
| **Phone overhaul** (2026-10-22) | The owner's design "Lightning on your phone": a tab bar of words (Overview, Budget, Add, Transactions, More), Add in its middle; every tab opens on one hero figure with a calm sentence (Overview: Safe to spend); a month stepper whose month opens Choose period; tabs in words; arrow chips on rows, no ".00"; More holds the other sections with their figures. Supersedes icon-only tabs (2026-10-15). Guideline 3.34 Part C; step 2 in [3AD](../issues/3-polish-and-arabic/3AD-phone-overhaul-step-2.md). |
| **Fewer steps to set up** (2026-10-06) | Recovery key shown once and confirmed with a press. One password on every device. |
| **Edit-journal connection and cost** (2026-10-16) | Pairing follows the Local pairing decision above. Saved keys authenticate routine sync without another pairing prompt. Prefer the reachable paired home on the local network, then use free-tier cloud delivery. Workers Free and SQLite Durable Objects only: no R2 or paid subscriptions. Exhausted cloud quotas pause delivery while local edits remain saved. Live cloud configuration can wait while development continues locally. |
| **Fingerprint, gam'eya and zakat** (2026-10-14) | Android offers fingerprint unlock as an option; the password and recovery key always still work. Gam'eya is built on the CD backbone with the interest rate optional (none by default). Zakat is an estimate by the common rule, off until turned on in Settings. |
| **Order to Google Play** (2026-10-06) | M1 phone and PC connected; M2 daily recording on the phone; M3 bank SMS into the ledger; then beta and Google Play. The owner reviews at each milestone. |

**Multiple devices (phone as home), planned and partly built.** One codebase on PC and Android; the phone holds the accepted encrypted ledger and one paired PC borrows it. Build status is in the Roadmap. Design, lend safety, hand-back, bank SMS: [multiple_devices.md](../issues/4-edit-journal-and-devices/4B-multiple-devices.md). **Edit anywhere, one home confirms** (owner-requested revision 2026-10-07; opt-in local integration and review packages built, validation recorded in PR #97; cloud delivery remains a placeholder): [edit_journal.md](../issues/4-edit-journal-and-devices/4A-edit-journal.md). A server or cloud copy is outside version 1.

Section 13 milestone 1 (owner approved 2026-10-14) stays inside existing workflows: optional salary/payday setup, learned bank CSV presets, Export all data under Your data, and instalment purchases/early payoff under Loans. No new default tabs or dashboard cards. The owner also approved recognising historical loan repayments from their cash dates; Mohab’s annual growth becomes 383,284 EGP (42,000 more), with cash unchanged. Later milestones cover optional reminders/confirmations, then deeper analytics.

<a id="what-you-can-do-today"></a>
## 3. What you can do today

Specs live in [Architecture](ARCHITECTURE.md); terms in the [Glossary](GLOSSARY.md).

- **Accounts and ledger:** accounts with starting balances; money in, out, internal transfers; edit, void, restore, bulk select, search; check an account against the bank's balance (small gaps become one adjustment).
- **CSV import:** one signed or separate in/out columns; one decision per new name; duplicates flagged; waiting reviews can be continued or discarded.
- **Budget:** Planned, Spent, Left in plan; amount or %; carryover; All time, YTD, Monthly, Custom; savings target and goals protected; Fill this month; low-confidence estimates marked.
- **Cash planning:** Safe to spend, What you owe, next 30 days, three-month forecast; Recurring bills, subscriptions and income (suggested, never created on their own); Loans with payoff date; Reserves with the emergency fund.
- **Needs you (Overview):** the one review inbox: statements waiting, uncategorized transactions, bills due, missing prices, plan problems; grouped by kind, each kind with several opening its own page.
- **Financial health:** named figures with profile-owned limits and six completed months of trend. No score.
- **Gam'eya (savings circle):** one account per circle with its terms (members, instalment, your turn, payout, optional interest); record each instalment and your payout as transfers; the circle page says who owes whom; Gam'eya paid in counts in Holdings value, Gam'eya still to pay in What you owe; instalments and the payout join Cash planning and a missed instalment appears under Needs you.
- **Investments:** buy, sell, dividends; prices fetched, typed or from shared files; Net gain or loss; Holdings after sale; target allocation; certificates and time deposits per certificate; US stocks priced in USD with price and FX parts of the gain (v1.1).
- **Currencies:** foreign cash with dated rates, Convert, per-currency position with realized and unrealized FX gain (v1.1).
- **Held for others** and **cash ownership:** reassign cash between you and a saved person, or record an expense paid for you.
- **Gold:** pieces with weight, karat and cost; a piece can be marked as worn.
- **Zakat:** an estimate by the common rule (2.5% at or above 85 g of 24K gold) from your position; zakat day, what you paid in the Zakat category and what is still to pay; one dated line in Cash planning. Accounts › Zakat; no ruling, Hijri dates not built.
- **Rules:** Settings › Rules file counterparties by condition.
- **Search and type faster:** Ctrl-K, #tags, sums in amount fields, privacy mode (the eye).
- **Arabic and phone:** the whole app in English or Egyptian Arabic, PC and phone; the phone records daily, reads CIB and NBE bank SMS with permission and hands the ledger to a PC over local Wi-Fi.
- **Profiles and release:** encrypted named profiles with recovery key; Windows ZIP (`Lightning.exe`, no Python) and signed Android APK published together from one tested commit (beta, 1.0.0-beta.1). Still open: ordinary-Windows recovery/fault acceptance, legacy import. Use an independent backup.
- **Samples:** `python -m lightning --demo` (Mohab's last three months); an empty profile can load Mohab's year (1 January to 2 October 2026) or the stories of Amr, Abdelrahman, Menna or Fatma. Mohab's year holds one of every part of Lightning: ten accounts of every kind (a dollar account bought with pounds, a flat valued by hand), goals (one paid, two saving), a gam'eya, zakat, a rule, a reimbursement claim, Mom's money and a grocery bill she paid, a laptop on instalments with an early payment, investing targets and a monthly goal, a saved #eid report and a statement still waiting for decisions. `tests/test_mohab_sample.py` keeps it that way: a new feature gets sample data there.

<a id="period-and-fixed-horizon-visuals"></a>
Owner decision (2026-10-24, 7Q): Needs you supports Mark as reviewed, Snooze until a chosen date, and Restore from Reviewed and snoozed. Reviewed reminders return when their situation changes; snoozes wake on their chosen date. These preferences change inbox/reminder visibility without recording payments or resolving the financial issue.

Owner decisions (2026-10-24, 7P / 3AG): exports use plain Arial 11 left alignment and readable names before mapping IDs; category levels are separate columns. Settings groups comprehensive export and empty-profile workbook onboarding in Move your data, with a narrower page and compact AI export/copy/edit controls; the prompt editor is a popup. Holdings rows show one clean line without secondary annotations, names turn blue on hover without underlines, and grouping uses one dropdown. Implementation and import boundaries: [Architecture › CSV import and export contract](ARCHITECTURE.md#csv-import-and-export-contract).

## 4. Period and fixed-horizon visuals

The period picker (All time · YTD · Monthly · Custom) drives most visuals. A few keep a fixed horizon, and each section header says which.

| Follows the period | Fixed horizon |
|---|---|
| Overview: stat cards, position cards (as of the period end, never after today), Cash flow, Investments section | Overview: Net worth over time (12 month ends up to the period end); Where money in went's last six months; Month by month |
| Budget: KPI cards (a month: everyday pace and its bills), Spent of plan | Budget: plans are monthly; longer periods add months, each month's left in plan |
| Investments: waffle, Net gain or loss, allocation and biggest holdings (as of period end), money and value by class | Portfolio value sparkline (last 6 months); Dividends (year to date); Return since first investment (plain before 365 days, annualized XIRR afterward, with days held); horizon bar (today) |
| Expense analysis: KPI cards, treemap, now against usual, daily calendar or monthly summaries | "Usual" is the 6 whole months before the period; usual range, small multiples, heatmap use the 12 before it |
| — | Holding page: whole history up to 24 month ends; sparklines last 6 |

A sparkline never follows the period. A comparison uses earlier months; a partial period uses matching calendar days, labelled so far with neutral comparison chips.

<a id="the-questions-lightning-answers"></a>
## 5. The questions Lightning answers

Each tab answers one main question, then its follow-ups. Reviewed 2026-10-13; `tests/test_mohab_year.py` checks the answers, so only open gaps are listed below.

| Screen | Main question | Leads with |
|---|---|---|
| Overview | Where do I stand, and what needs me? | Needs you, Net worth, Free cash, what it is made of, cash flow |
| Expense analysis | Where did my money go? | Money out, ranked categories, change from last period |
| Budget | Am I on plan? | Left in plan, everyday spending against pace, categories over plan |
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
| A merchant or a few categories I care about | Built locally: named live-date register views, matching report and export |
| A refund: did my spending go down? | Partial: it lowers the category in the month the refund arrives, not the purchase month (Mohab 13) |
| Work spending my employer owes me back | Built locally: explicit claims and partial receipt/refund links list outstanding amounts |
| What about next month's plan? | Partial: rules repeat; a future month cannot be opened |
| Where should the rest of my income go? | Built locally: optional funded payday preview using actual cash, with reserve top-ups |
| Have I actually set aside the goal's monthly amount? | Partial: nothing asks him to assign it |
| I paid from the emergency fund: what now? | Partial: nothing reminds him to refill (Mohab 14) |
| Pay the loan off early | Missing: no lump-sum payment |
| When does my certificate mature? | Portfolio dates and explicit interest receipt reconciliation built; legacy account-level conversion remains |
| How are my dollar savings and US stocks doing? | Built in v1.1; open: bank-imported pairs across currencies, Europe and GCC listings |
| No pay this month: does the average fall? | Known gap: zero-income months are skipped by the average (Mohab 27) |
| Was I paid my raise? | Partial: the scheduled payment stays Due until linked by hand |
| Is my salary late? | Left out by decision |
| Stale prices | Needs you flags prices older than about two months; month-end price gaps are listed |

Early pay, raise and rent changes need explicit confirmation by design: Lightning suggests, Mohab confirms, neither plan nor reserve changes silently. Left open by the 2026-10-05 audit: a payment scheduled on the 31st moves to the 30th after a shorter month and stays there.

<a id="reference-workflow-a-month-with-mohab"></a>
## 6. Reference workflow: a month with Mohab

**Mohab**, 31, salaried, Cairo: 45,000 EGP a month from ACME Egypt into CIB; a cash wallet and Vodafone Cash; an NBE 3-year certificate; a THNDR account with COMI, Fawry and a money market fund; an L'Azurde ring and a gold pound; 10,000 EGP of his mother's money in CIB; rent, internet, phone, electricity, and a 24-month car loan.

`tests/test_mohab_year.py` (read its docstring) runs steps 1–36 through the screens, one test per step. It judges answers, route from the Overview, effort, speed, simplicity, clarity and UI. When a gap is fixed, change its assertion and the Today column together.

**Steps 1–10, one ordinary month (July–September 2026):** open six accounts (dates as `1/7`); import 40 CIB rows (39 posted, 1 skipped, Mom's 10,000 is Held for others); move money to THNDR and buy COMI, Fawry and a fund; record the ring and the gold pound; cash and Vodafone Cash spending; month-end prices; a 20,000 emergency fund and the budget (Free cash = Cash you own − Reserves − Bills due); track recurring items and the car loan (What you owe 60,000); on 2026-10-06 mark salary, rent and a loan payment paid (Net worth moves only by +45,000; loans still to pay 57,500); read every tab, Checks pass.

**Steps 11–36, October 2026 to September 2027:**

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
| 32 | 30 Sep | Joins a 10-member, 2,000 EGP gam'eya and takes the third pot | Answered: the missed instalment shows once under Needs you; Net worth unchanged; 14,000 under What you owe |
| 33 | 30 Sep | Claims the work Uber ride back from ACME and links the receipt | Answered |
| 34 | 30 Sep | Saves a register view of everything tagged #eid | Answered |
| 35 | 30 Sep | Sets the investing mix he aims for (50% stocks, 30% gold) | Answered |
| 36 | 30 Sep | Pays 5,000 early against the phone | Answered |

The dollar steps are not yet inside the year (NOW.md, Next 3). User feedback batch 001 is checked by nine named screen assertions; loading speed, scroll position, compact review rows, chart colours and register balance are judged on a real PC.

**Not scripted:** the NBE certificate maturing (forecast only; he enters redemption and interest by hand); paying the car loan off early (covered separately by milestone regression/browser tests); payslip deductions (record net pay).

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

Bank sync and bill negotiation are not adopted: local CSV stays the foundation. "Safe to spend" must always say which obligations and income it includes. Certificate projections use an actual/365 estimate, are never posted, and bank interest is reconciled only through explicit existing-receipt links, never assumed received.

<a id="ux-plan-guideline-36"></a>
## 8. UX plan (guideline 3.6)

From the full UX review of 2026-10-03 (Mohab's year at 1,366 × 768) and the tab-by-tab audit of 2026-10-06. Structure is two levels (2026-10-06).

**The user's route:** Where do I start? → Is my money in? → How much can I spend before payday? → What is due? → Am I on plan? → Where did it go? → How are my investments? → Is my data right? Each tab answers one; Needs you is the to-do list across them.

**Done (2026-10-03 to 2026-10-07):** all ten ranked items, in short: Get set up first run; one decision per imported name; category picker; bulk set category; one name, one number; two-line registers; honest price warnings; Reserves table with Refill; whole-EGP words and numbers; the tab-by-tab fixes. Brand audits since are in the CHANGELOG (guideline 3.28–3.30, v1.1 brand pass).

**Owner decisions (2026-10-03):** Budget's low-confidence estimates count in Left in plan with a "!"; the Overview's Investments section is one row of figures linking to the tab.

**Still open:** import button says "Post ready rows" while undecided rows post as Unaccounted; bulk counterparty edit.

<a id="upcoming-projects"></a>
<a id="roadmap"></a>
## 9. Plan and roadmap

The plan is [issues/](../issues/INDEX.md): numbered milestones in the order they are worked on, each with its action plan
of coded items (**3C**, and **3C1** one step down). The owner picks the order; [issues/README.md](../issues/README.md) has
the rules. In short:

1. Easy to contribute · 2. Safe for real money · 3. Polish and Arabic · 4. Edit journal and devices · 5. Investments ·
6. Market data · 7. Planning, import and search · 8. Website · 9. Later.

**Shipped so far:** foundation and cash accounts; Budget; reports and corrections (checked history); manual investments
and the instrument catalogue; price packs, foreign cash, Convert, FX positions and US stocks (v1.1); certificates and
deposits; CSV import and Cash planning; search and Ctrl-K; multiple devices M1–M3 (lend, hand back, bank SMS); the paired
apps beta; Arabic on PC and phone; financial health; undo and redo; rules with conditions; layered import match; weekend-aware
schedules; Fill this month; entry helpers; gam'eya and zakat; and the five owner-approved smarter workflows (2026-10-15:
dated cash warnings, undo/review/provenance, reserve/bill/CD/reimbursement links, optional cash funding, saved views and
weekly review). Detail: [CHANGELOG](../CHANGELOG.md) and [Architecture](ARCHITECTURE.md). Where each idea came from:
[Competition](COMPETITION.md).

## Cosmetic marketplace owner revision (2026-10-24)

Appearance uses swappable, approved parts with fixed layout and financial semantics. Themes are intended to ship in the app; the website sells account-wide permanent ownership, then a temporary random code delivers a signed offline unlock over an initial online exchange. No device cap or repeat charge. Nile Nocturne and Royal Obsidian & Gold are the first design tests; pricing and release integration remain uncommitted. The site handles InstaPay plus a customer reference/WhatsApp receipt and separate owner settlement confirmation, with a stated final-purchase policy subject to required rights and error correction. Infrastructure status: Architecture › Cosmetic parts and offline ownership; remaining work: 8J.

### Website gamification revision (2026-10-24)

The website adds consented, moderated community stories with optional author-provided LinkedIn links. Accepted stories can earn recognition points once; a URL alone earns nothing. Recognition points do not fund purchases. Mono becomes the only free website palette; existing paid ownership and previously equipped free palettes are preserved. Account access uses a compact avatar/icon dropdown, and Features is linked as a card inside Guides. Top-up receipts move from WhatsApp to private website uploads, with the member email in the InstaPay note and the payer InstaPay address recorded for reconciliation; owner settlement confirmation remains mandatory.

**Market owner revision (2026-10-25).** Both markets, main-site Marketplace (Part B) and For Geeks (Part D), share one structure (not one look: each keeps its own guideline) from the owner's market sheets: Your look beside the wallet, tabs (Themes, Banners, Frames, Badges, Owned), the two app themes in testing featured without a price, Details showing a theme on the website, the PC app and the phone, Try it for the visit with nothing saved, and a buy that says how many coins are missing. No Threads currency: coins keep their name and are drawn as a pixel-art cotton boll. Themes are shared, looks are not: one purchase dresses both sites, each drawing its own version (For Geeks its terminal palette; the main site a light and a dark side that follow the light/dark switch). A theme a member owns and equips may be worn across the main website (an owner exception to Part B's fixed palette); good and bad keep their colours. Five palettes are on sale (Paper, Frost, Meadow, Nile, Garnet) until each works on both sites; the other nine are archived but kept by their owners. How a theme is made: [guideline/themes.md](../guideline/themes.md).
