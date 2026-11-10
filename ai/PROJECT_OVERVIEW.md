# Lightning — Project Overview

**Last reviewed 2026-10-23 · source 1.4.4 · latest published beta 1.4.2** ([published Windows and Android beta](https://github.com/LightningEg/Lightning-downloads/releases/tag/v1.4.2)).

What Lightning is, who it is for, and where it goes. What each screen must answer: [Users' main questions](../issues/3-polish-and-arabic/r14-users-main-questions/report.md). Technical contracts: [Architecture](ARCHITECTURE.md). Look: [guideline](../guideline/). Terms and figures: [Glossary](GLOSSARY.md). Shipped changes: [RELEASES.md](../RELEASES.md) (people) and [ai/changelog/](changelog/) (detail). Hand-off between AIs: [NOW.md](../NOW.md). The plan and open items: [issues/](../issues/INDEX.md).

## Contents

Read one section: `grep -n '^## ' ai/PROJECT_OVERVIEW.md`, then read from that line.

| Section | Read it when |
|---|---|
| 1. What Lightning is | You are new to the product |
| 2. Product decisions that must hold | You change any figure, rule or flow |
| 3. What you can do today | You need the feature list |
| 4. Period and fixed-horizon visuals | You change a chart, card or the period picker |
| 5. Reference workflow: a month with Mohab | You change Mohab's test or a screen he uses |
| 6. Compared with the best budgeting apps | You plan a feature |
| 7. UX plan (guideline 3.6) | You take a UX item |
| 8. Plan and roadmap | You pick the next work or finish a milestone |
| 9. Owner checks held for testing | A milestone works end to end, or you plan a release |
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
| **Real data is welcome** (2026-10-28) | People use Lightning with their own statements; the site and app never tell them not to. Milestone 2 keeps hardening what protects that data. The account invitation on Home stays: the app needs no account, so it costs nothing to say no. |
| **Legacy launch is samples only** (2026-11-04, OW-2AB) | Real data uses encrypted profiles (`--profiles` from source). The old browser entry point permits only explicit `--demo` or `--sample`; bare launch and `--db` stop before touching files. Existing legacy databases remain untouched; migration/import is separate IT-2C work. Plaintext tests can opt into the profile database's owning-thread and closed-session checks. |
| **Owner decisions, 2026-11-08 (round two)** | Lending: one "Owed to you" account per person (`RECEIVABLE`), splits as one entry with only your share as spending, "you owe them" below zero in What you owe (NF-12G). Import review opens on question cards with bulk Uncategorized for small leftovers (NF-7AB); NF-7C closed. Closed-app reminders carry days and kinds only (NF-3AU). Missed-salary row, zakat 12-month instalments switch (off), optional loan rate; pay-cycle months and this-month-only Safe to spend not now (IV-3H). Inflation check first (HE-6). A stuck restore may go back to the pre-restore copy (IT-2C). Hijri via Umm al-Qura, zakat day follows a Hijri pick; gold nisab default, typed silver price (NF-9D). Personal commit email left as is; working documents stay public (IT-1E). Matching Papyrus/Dendera set pieces (NF-10D). "Counterparty" becomes "Payee". Rows drop ".00" on PC too, Arabic ٪ and Arabic-Indic chip digits, dark stays with themes, neutral Arabic address (IV-3BK). Post the 37 contributor issues (IT-1N). |
| **Owner decisions, 2026-11-09 (audits r30, r31, r32)** | Investments: build the blockers first (a certificate already owned NF-12I, a second gold bar BT-12H, one *Add investment* IV-12K); treasury bills, bonds, a business share and insurance or pension plans get no model, each stays an *Other* holding with a typed value that can be re-appraised. Logging: build Repeat and Save and add another (NF-7AM) and Save now, sort later (NF-7AN); bank messages Lightning is sure about save themselves, marked and undoable (NF-7AO), which replaces review-before-posting for those messages only; app notifications and receipt photos not chosen. Budget and Cash planning (r32): the payday funding page is redesigned as one short step (IV-12Q1); Fill from the three-month average (NF-12R) and a warning before a category runs out (NF-12S) go in the plan; a bills calendar not chosen. Second round: Home leads with the everyday budget, Safe to spend leads Cash planning (IV-12P); a certificate paid at maturity grows in value as an estimate (IV-12J3); property lives under Investments and a flat on instalments counts only what was paid, the rest in the forecast and not a debt (NF-12M); a dollar payment is recorded in dollars with the balance rated in pounds (NF-7AK3); a bank message's stated balance is compared with the account as a quiet To do row (NF-7AP). Accounts (r34, 2026-11-10): a cash or wallet account may adjust its balance by any size, filed as Unaccounted Spending, banks keep the limit (IV-12V); a positive amount on a spending category asks once, refund or payment (IV-12W). |
| **Human dates on screens; ج.م in Arabic** (2026-11-08, OW-3BJ) | Screens show dates as people say them ("8 Nov", "November 2026", "Yesterday"); fields and exports keep yyyy-mm-dd. Arabic labels the currency ج.م, not EGP. Both change guideline A06.1/A06.2 in both repos before any template changes. |
| **In your accounts is the sum of the rows** (2026-11-05, BV-3AQ) | In your accounts is what the account balances add up to, a circle you still owe counted below zero, on Accounts, the sidebar and More. Accounts reconciles it to What you own: less held for others, plus Gam'eya still to pay (which sits in What you owe). Net worth is unchanged. |
| **Branches** (2026-10-12) | Work on `who/feature`, merge finished work into `main`. [AGENTS.md](../AGENTS.md) section 6. |
| **Arabic is for Egypt** | English and Egyptian Arabic for the same profile; the website links matching pages. Arabic reads right to left; money, dates, codes and identifiers keep their natural order. Names: [Glossary](GLOSSARY.md#العربية--المسرد-العربي). |
| **Feedback screenshots stay private** | Up to five images per ticket, stored in the Apps Script owner's private Drive folder, linked in the feedback Sheet. The website repo owns it. |
| **Savings and reserve matching** (2026-10-19) | The waffle shows savings only, including savings allocated to investments, with positive Overspent figures and darker spending squares when spending exceeds income. Reserve matching can combine account, counterparty and category; all selected criteria must match. |
| **KPI cards compare** (2026-10-19) | Every KPI card shows a comparison (guideline 3.32, A08): five fixed slots, no icon tile; two to four cards fill a row; a key note never forms a row of its own. Budget's day rate counts only everyday money, not bills still to pay in the plan. The savings waffle lives only behind the Overview's Savings rate. Price and net-worth charts keep their axis from zero and name the change. [3Q](https://github.com/LightningEg/Lightning/blob/e09ddd1/issues/3-polish-and-arabic/3Q-visual-audit-cards-that-compare.md) builds it. |
| **Answer first** (2026-10-21) | Every page opens on its answer: header with a status sentence and the dates, the Lead with its working, Needs you, KPIs, then details; one home per figure (guideline 3.33, A09). KPI tiles 2 × 2 on the phone. Built (3W). Where money in went (beside the last six months, ticket 78) and Month by month (tickets 79, 86) moved from the Overview to Spending (owner, 2026-10-21). |
| **Arabic body face** (2026-10-19) | Arabic body text is Noto Sans Arabic, more readable than IBM Plex Sans Arabic, which is gone; Readex Pro stays for titles and figures (A06.2). |
| **One ledger** | Registers, budget actuals, investments, Overview and reports are views of one transaction ledger. |
| **Other people's money** | *Held for others* stays in the account balance, is left out of *What you own*, and is not income, spending or money owed to you. |
| **Obligations count, forecasts never do** | Bills due and loans still to pay make *What you owe*: bills due come off Free cash, What you owe off Net worth. Loans are schedules, not debt accounts; a payment is spending when paid. Credit cards, loan-interest accounting and receipt photos are out of scope; CD interest is an estimate. Money lent to others and costs split with others come into scope (owner, 2026-11-06, OW-12F; design NF-12G). |
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
| **Each app fetches its own Gulf and European prices** (2026-11-04) | Saudi, Gulf and European holdings are priced by the app itself from the country's whole board and history, as EGX and US are; nothing is republished, so the packs stay unpublished until 6B. |
| **One row per broker, pockets as tabs** (2026-10-16; layout 2026-11-04) | A broker holds a cash pocket per currency (no margin; convert, then buy). Its page leads with a small overview in the main currency, then one tab per pocket; a broker with one pocket keeps the ordinary page. Broker statements: Interactive Brokers first. |
| **Local only** (2026-10-05) | Data stays on the user's computer, never in Git. Encrypted profiles under Documents/Lightning, password of any length; a 12-digit recovery key plus a security question reset it. One thing opens a profile; two change its password, question or key. Architecture › Encryption. |
| **Two levels, few settings** (2026-10-06) | Six sections, at most five tabs each, no third level; settings behind a tab's gear; a default before a setting; icons for row actions; one choice, one field. Architecture › UI contract. |
| **Your data first in Settings** (owner, 2026-10-29) | Swap Your data and Data checks back: Your data, Rules, Categories, Counterparties, Data checks. Settings opens on Your data; supersedes the 2026-10-28 Data checks default. |
| **Locked certificates** (2026-10-14) | Show the owned value and unlock date separately beside If you sold today; do not count it as saleable cash. |
| **Phone has its own design** (2026-10-06, 2026-10-07) | Part C of the guideline; never the PC layout squeezed. Every icon has its word (alone only if universal). The tab bar, Add and the Overview's order: Phone overhaul below. |
| **Phone overhaul** (2026-10-22) | The owner's design "Lightning on your phone": a tab bar of words (Overview, Budget, Add, Transactions, More), Add in its middle; every tab opens on one hero figure with a calm sentence (Overview: Safe to spend); a month stepper whose month opens Choose period; tabs in words; arrow chips on rows, no ".00"; More holds the other sections with their figures. Supersedes icon-only tabs (2026-10-15). Guideline 3.34 Part C; step 2 (3AD) is done: quick add and the transaction sheet in 3AN3, swipe to set a category in C08.7 (guideline 3.39). |
| **Phone declutter** (owner, 2026-10-29, left to Claude) | Quick actions and quick info first; analysis one tap away. D1: Overview's breakdown rows open sheets, not folds in folds. D2: Transactions keeps its filter chips; Money in and out become one line. D3: More stays flat under headings. D1 and D2 change Part C in both repos first: [Audit 10](../issues/11-phone-ux/r17-phone-tab-audit/report.md), IV-3AL. |
| **Phone Investments order** (owner, 2026-11-06) | Holdings come before the chart: hero, month stepper, holdings, then the chart, so the working list starts on the first screen (Holdings at y=413, was 753 at 360 x 800). Replaces the earlier overhaul order. [Audit r24 F10](../issues/12-desktop-ux/r24-desktop-phone-ux/report.md); `tests/test_phone_investments.py`. |
| **Plan and reports in one tree** (owner, 2026-11-06; built) | One folder per big picture in `issues/`. Inside it: the report (`r<N>-subject/report.md`, with its evidence) and its items, each named by tag and a real name (`BT-2AF-asset-value-follows-dated-estimate.md`). Codes are opaque ids: they never change and stay with the item when it moves; folder numbers only seed new codes (`python tools/issues.py next <n>`). Phone UX (11) and Desktop UX (12) are the two new folders; older folders keep their numbers. The catalogue is `issues/REPORTS.md`; `reports/` no longer exists. Rules: [issues/README.md](../issues/README.md). |
| **Home and sheets** (2026-11-05, 3G5/3G6) | The Overview keeps its answer-first layout and adds a "since your last visit" line, not three heroes. One category sheet serves Budget, Spending and Transactions; one bill sheet follows. |
| **The phone is its own product** (2026-11-06, IV-3AY) | The phone shares the PC's services, figure names, tokens and profile, not its layout. Five slots: Home, Budget, Add, Activity, Money (More becomes Money, Settings behind a gear). Home is always today: Safe to spend, To do, Latest, one This-month row; no month stepper, no Net worth (it leads Money). Bills late more than 7 days or from before the last payday become one catch-up question. Part C is rewritten in both repos before the screens are built. Design: `issues/11-phone-ux/r25-phone-ux-architecture/report.md`. |
| **No health score** (2026-11-04, 3AD4) | Health stays a set of compared ratios; there is no 0-100 score. |
| **Fewer steps to set up** (2026-10-06) | Recovery key shown once and confirmed with a press. One password on every device. |
| **Edit-journal connection and cost** (2026-10-16) | Pairing follows the Local pairing decision above. Saved keys authenticate routine sync without another pairing prompt. Prefer the reachable paired home on the local network, then use free-tier cloud delivery. Workers Free and SQLite Durable Objects only: no R2 or paid subscriptions. Exhausted cloud quotas pause delivery while local edits remain saved. Live cloud configuration can wait while development continues locally. |
| **Fingerprint, gam'eya and zakat** (2026-10-14) | Android offers fingerprint unlock as an option; the password and recovery key always still work. Gam'eya is built on the CD backbone with the interest rate optional (none by default). Zakat is an estimate by the common rule, off until turned on in Settings. |
| **Stay signed in on the phone** (owner, 2026-11-01) | "Keep me logged in on the phone as long as I don't log out, not every time I close it." The phone keeps the profile open across closes and never idles it out; Lock signs out. Guarded by the phone's own screen lock (the key is usable only while the phone is unlocked). Not on the PC. |
| **Order to Google Play** (2026-10-06) | M1 phone and PC connected; M2 daily recording on the phone; M3 bank SMS into the ledger; then beta and Google Play. The owner reviews at each milestone. |
| **Google Play launch** (owner, 2026-11-09, r29) | Bank SMS reading ships in the first Play release: declare READ_SMS under "SMS-based money management" with a video; the reader filters people's numbers in the query and shows its disclosure first (NF-11B2). Themes are sold inside the Play build with Google Play Billing, and the Play build has no website price or link (NF-11B3). Phone rows get a category mark in the disc, keeping the in/out colour; Part C changes in both repos before code (IV-11D6). Phone Settings gets an in-app Delete this profile (NF-11J). Home's hero says about how much a day with Budget's own everyday figure (EverydayBudget.per_day), never Safe to spend divided by the days, so BV-12A's one daily allowance holds (IV-11E); under it, in the seam's place, the payday meter (IV-11D1). |
| **One purchase per person** (owner, 2026-11-09) | A theme bought on Google Play unlocks every profile of that Google account; a website purchase unlocks every profile its account claims (25% extra seats end; cap 10). Website themes reach the Play build only through the profile's synced licence (no code box there). A Play refund stops new unlocks; issued licences stay. One EGP price on Play and the website. [NF-10H](../issues/10-looks-and-store/NF-10H-one-purchase-per-person.md). |

**Multiple devices (phone as home), planned and partly built.** One codebase on PC and Android; the phone holds the accepted encrypted ledger and one paired PC borrows it. Build status is in the Roadmap. Design, lend safety, hand-back, bank SMS: [multiple_devices.md](../issues/4-edit-journal-and-devices/NF-4B-multiple-devices.md). **Edit anywhere, one home confirms** (owner-requested revision 2026-10-07; opt-in local integration and review packages built, validation recorded in PR #97; cloud delivery remains a placeholder): [edit_journal.md](../issues/4-edit-journal-and-devices/NF-4A-edit-journal.md). A server or cloud copy is outside version 1.

Section 13 milestone 1 (owner approved 2026-10-14) stays inside existing workflows: optional salary/payday setup, learned bank CSV presets, Export all data under Your data, and instalment purchases/early payoff under Loans. No new default tabs or dashboard cards. The owner also approved recognising historical loan repayments from their cash dates; Mohab’s annual growth becomes 383,284 EGP (42,000 more), with cash unchanged. Later milestones cover optional reminders/confirmations, then deeper analytics.

<a id="what-you-can-do-today"></a>
## 3. What you can do today

Specs live in [Architecture](ARCHITECTURE.md); terms in the [Glossary](GLOSSARY.md).

- **Next step where a figure raises the question** (NF-3AZ, 2026-11-08): a posted salary opens one payday proposal (bills, everyday spending, emergency and goals, left unassigned, before and after); a statement line links to the payment already captured by SMS; a repeated category correction offers a rule with its past matches; a bill opens one sheet with its reserve and budget effect; a reimbursable expense offers Create claim and a receipt offers Match reimbursement; Can I afford this checks an account on a date; the emergency refill offers instalments; a maturing certificate shows a forecast, and choices only after the redemption is recorded; an investment result lists its parts and rows; Needs you groups by Money at risk, Unreconciled events and Optional cleanup on the Overview, Needs you and Weekly review, and reviewed or snoozed items stay counted as open.
- **Accounts and ledger:** accounts with starting balances; money in, out, internal transfers; edit, void, restore, bulk select, search; check an account against the bank's balance (small gaps become one adjustment).
- **Statement import:** CSV, literal .xlsx workbooks and aligned CIB text PDFs use one review; non-text PDFs have a local Copy/Edit AI-to-CSV prompt with no automatic upload. CSV uses one signed or separate in/out columns; one decision per new name; duplicates flagged; waiting reviews can be continued or discarded.
- **Budget:** Planned, Spent, Left in plan; amount or %; carryover; All time, YTD, Monthly, Custom; savings target and goals protected; Fill this month; low-confidence estimates marked.
- **Cash planning:** Safe to spend, What you owe, next 30 days, three-month forecast; Recurring bills, subscriptions and income (suggested, never created on their own); Loans with payoff date; Reserves with the emergency fund.
- **Needs you (Overview):** the one review inbox: statements waiting, uncategorized transactions, bills due, missing prices, plan problems, recurring/rule offers, reserve refills and Financial health's alert bands; grouped by kind, each kind with several opening its own page. Import confirmation names the bills it settled; certificate Match all returns to the inbox. Existing savings reminders cover the same issue once.
- **Financial health:** named figures with profile-owned limits and six completed months of trend. No score.
- **Gam'eya (savings circle):** one account per circle with its terms (members, instalment, your turn, payout, optional interest); record each instalment and your payout as transfers; the circle page says who owes whom; Gam'eya paid in counts in Holdings value, Gam'eya still to pay in What you owe; instalments and the payout join Cash planning and a missed instalment appears under Needs you.
- **Investments:** buy, sell, dividends; prices fetched, typed or from shared files; Net gain or loss; Holdings after sale; target allocation; certificates and time deposits per certificate; US stocks priced in USD with price and FX parts of the gain (v1.1). Brokers that span currencies: one row per broker with a pocket per currency, Gulf and European shares priced by the app, a USD view of the whole page, and Interactive Brokers statement import with a positions check (NF-5G).
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
| Investments: waffle, Net gain or loss, allocation and biggest holdings (as of period end), money and value by class | Portfolio value sparkline (last 6 months); Dividends (year to date); Return since first investment (plain before 365 days, annualized XIRR afterward, with days held and explicit ambiguous/unavailable explanations); horizon bar (today) |
| Expense analysis: KPI cards, treemap, now against usual, daily calendar or monthly summaries | "Usual" is the 6 whole months before the period; usual range, small multiples, heatmap use the 12 before it |
| — | Holding page: whole history up to 24 month ends; sparklines last 6 |

A sparkline never follows the period. A comparison uses earlier months; a partial period uses matching calendar days, labelled so far with neutral comparison chips.

<a id="the-questions-lightning-answers"></a>
**Questions each screen answers and open gaps:** [Users' main questions](../issues/3-polish-and-arabic/r14-users-main-questions/report.md).

<a id="reference-workflow-a-month-with-mohab"></a>
## 5. Reference workflow: a month with Mohab

**Mohab**, 31, salaried, Cairo: 45,000 EGP a month from ACME Egypt into CIB; a cash wallet and Vodafone Cash; an NBE 3-year certificate; a THNDR account with COMI, Fawry and a money market fund; an L'Azurde ring and a gold pound; 10,000 EGP of his mother's money in CIB; rent, internet, phone, electricity, and a 24-month car loan.

`tests/test_mohab_year.py` (read its docstring) runs steps 1–36 through the screens, one test per step. It judges answers, route from the Overview, effort, speed, simplicity, clarity and UI. When a gap is fixed, change its assertion and the Today column together.

**Steps 1–10, one ordinary month (July–September 2026):** open six accounts (dates as `1/7`); import 40 CIB rows (39 posted, 1 skipped, Mom's 10,000 is Held for others); move money to THNDR and buy COMI, Fawry and a fund; record the ring and the gold pound; cash and Vodafone Cash spending; month-end prices; a 20,000 emergency fund and the budget (Free cash = Cash you own − Reserves − Bills due); track recurring items and the car loan (What you owe 60,000); on 2026-10-06 mark salary, rent and a loan payment paid (Net worth moves only by +45,000; loans still to pay 57,500); read every tab, Checks pass.

**Statement follow-up (NF-7B, 2026-11-04):** Mohab chooses an Excel or supported text-based CIB statement, reviews and files the rows, then confirms; only confirmation changes cash. `tests/test_mohab_statements.py` covers both routes. A PDF without selectable text is rejected with a Copy/Edit AI-to-CSV prompt; Lightning performs no OCR or automatic upload.

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
## 6. Compared with the best budgeting apps

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
## 7. UX plan (guideline 3.6)

From the full UX review of 2026-10-03 (Mohab's year at 1,366 × 768) and the tab-by-tab audit of 2026-10-06. Structure is two levels (2026-10-06).

**The user's route:** Where do I start? → Is my money in? → How much can I spend before payday? → What is due? → Am I on plan? → Where did it go? → How are my investments? → Is my data right? Each tab answers one; Needs you is the to-do list across them.

**Done (2026-10-03 to 2026-10-07):** all ten ranked items, in short: Get set up first run; one decision per imported name; category picker; bulk set category; one name, one number; two-line registers; honest price warnings; Reserves table with Refill; whole-EGP words and numbers; the tab-by-tab fixes. Brand audits since are in the CHANGELOG (guideline 3.28–3.30, v1.1 brand pass).

**Owner decisions (2026-10-03):** Budget's low-confidence estimates count in Left in plan with a "!"; the Overview's Investments section is one row of figures linking to the tab.

**Owner decisions (2026-11-09, [r35](../issues/12-desktop-ux/r35-ux-against-users-questions/report.md)):** polish goes phone first, then the PC; every PC tab follows one skeleton (title, answer sentence, dates, the same controls in the same order) kept by a test (IV-12Y); a tab's answer fits one screen and the rest opens on request (IV-12Z); smart means all four, always as a suggestion the person confirms: notice and propose the next step, do repeated work (IV-12AA), explain every figure in place (NF-12AB), answer a typed question offline (NF-7AQ).

**Owner decision (2026-11-09, [r36](../issues/11-phone-ux/r36-figures-one-owner/report.md)):** "Left in plan" means Planned − Spent on every screen; the phone's Budget leads with everyday money under its own name, "Left for everyday" (BV-11L1).

**Owner decisions (2026-11-10, O1 "Figures must add up"):** Refill's filled button offers the plan's monthly Emergency fund top-up, the full safe amount under "Move more" (IV-12AA1/2); the emergency aim is six months on Reserves and Limits alike (three is only the Needs you warning). Cash available to assign is stated before the bills due outside the funds, and the payday proposal's Bills protected, To your plan, Emergency and goals and Left unassigned add up to it (BT-12AD).

**Still open:** import button says "Post ready rows" while undecided rows post as Unaccounted; bulk counterparty edit.

<a id="upcoming-projects"></a>
<a id="roadmap"></a>
## 8. Plan and roadmap

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
weekly review). Detail: [ai/changelog/](changelog/) and [Architecture](ARCHITECTURE.md). Where each idea came from:
[Competition](COMPETITION.md).

## 9. Owner checks held for testing

Owner, 2026-10-28: owner-only tasks are closed as items and held here. **Bring this list to the owner when we test a milestone end to end or prepare a release**; reopen an item only if a check fails. Each link is the item as it stood when held.

| Code | Check | Why it matters |
|---|---|---|
| [1B](https://github.com/LightningEg/Lightning/blob/9ca53bd/issues/1-easy-to-contribute/1B-owner-runs-security-setup.md) | Run `python tools/security_setup.py --apply` | Until run, the no-push-to-`main` rule, tag protection and secret scanning are not confirmed active |
| [1C](https://github.com/LightningEg/Lightning/blob/9ca53bd/issues/1-easy-to-contribute/1C-trial-contribution.md) | One trial contribution from the website to a merged PR (needs 1B) | Milestone 1's *done when* |
| [2B](https://github.com/LightningEg/Lightning/blob/9ca53bd/issues/2-safe-for-real-money/2B-promotion-durability.md) | Windows reboot drill, `tools/promotion_drill.py`, phases P1–P4 | Real-money gate (§4 of AGENTS.md); code and fault tests already pass |
| [3I](https://github.com/LightningEg/Lightning/blob/9ca53bd/issues/3-polish-and-arabic/3I-owner-check-first-run-and-import.md) | First run and import review on PC and phone | |
| [3AH](https://github.com/LightningEg/Lightning/blob/9ca53bd/issues/3-polish-and-arabic/3AH-visual-flow-acceptance.md) | Visual flow on real Windows/Android, English and Arabic, keyboard and screen reader | Browser evidence only so far |
| [3T](https://github.com/LightningEg/Lightning/blob/e09ddd1/issues/3-polish-and-arabic/3T-phone-guideline-breaks-audit-1.md) | Zakat's date uses the native picker on a real Android phone (shows the date, not mm/dd/yyyy) | Browser evidence only |
| [8C](https://github.com/LightningEg/Lightning/blob/9ca53bd/issues/8-website/8C-be-found-as-the-all-in-one-tracker.md) | Resubmit the sitemap; Reddit post; re-ask AI search after two weeks | |
| [8I](https://github.com/LightningEg/Lightning/blob/9ca53bd/issues/8-website/8I-guides-owner-checks.md) | Search Console impressions of the merged guide; read the Arabic topic pages | |

Owner *decisions* stay in the plan when they change what we build. On 2026-11-04 the owner delegated sensible decisions for report completion: income reversals reduce Money in (7S); source launch uses explicit `--profiles`, `--demo` or `--sample` modes; bare launch and every `--db` argument stop before opening data (2AB, the later approved #303).

## Cosmetic marketplace owner revision (2026-10-24)

Appearance uses swappable, approved parts with fixed layout and financial semantics. Themes are intended to ship in the app; the website sells account-wide permanent ownership, then a temporary random code delivers a signed offline unlock over an initial online exchange. No device cap or repeat charge. Nile Nocturne and Royal Obsidian & Gold are the first design tests; pricing and release integration remain uncommitted. The site handles InstaPay plus a customer reference/WhatsApp receipt and separate owner settlement confirmation, with a stated final-purchase policy subject to required rights and error correction. Infrastructure status: Architecture › Cosmetic parts and offline ownership; remaining work: 10A.

### Website gamification revision (2026-10-24)

The website adds consented, moderated community stories with optional author-provided LinkedIn links. Accepted stories can earn recognition points once; a URL alone earns nothing. Recognition points do not fund purchases. Mono becomes the only free website palette; existing paid ownership and previously equipped free palettes are preserved. Account access uses a compact avatar/icon dropdown, and Features is linked as a card inside Guides. Top-up receipts move from WhatsApp to private website uploads, with the member email in the InstaPay note and the payer InstaPay address recorded for reconciliation; owner settlement confirmation remains mandatory.

**Market owner revision (2026-10-25).** Both markets, main-site Marketplace (Part B) and For Geeks (Part D), share one structure (not one look: each keeps its own guideline) from the owner's market sheets: Your look beside the wallet, tabs (Themes, Banners, Frames, Badges, Owned), the two app themes in testing featured without a price, Details showing a theme on the website, the PC app and the phone, Try it for the visit with nothing saved, and a buy that says how many coins are missing. No Threads currency: coins keep their name and are drawn as a pixel-art cotton boll. Themes are shared, looks are not: one purchase dresses both sites, each drawing its own version (For Geeks its terminal palette; the main site a light and a dark side that follow the light/dark switch). A theme a member owns and equips may be worn across the main website (an owner exception to Part B's fixed palette); good and bad keep their colours. Five palettes are on sale (Paper, Frost, Meadow, Nile, Garnet) until each works on both sites; the other nine are archived but kept by their owners. How a theme is made: [guideline/themes.md](../guideline/themes.md). Owner, 2026-10-25: themes come in tiers priced for one-time buyers (Palette 300 coins = 60 EGP, Textured 600, Animated 1,000 later; 5 coins per EGP); the reasoning against about 3,000 EGP of monthly fixed cost is in the website repo's docs/payment-operations.md.

Report decisions delegated by the owner, 2026-11-04: early extra loan principal remains gross Money out but does not use the monthly plan; its fees do. Confirmed reserve funding also stays outside that plan, without changing the expense’s cash-flow classification (OW-7M).

Section 7 scenarios compare scheduled cash over 90 days with explicit income-delay, purchase and one-payment bill overrides. Variable spending and savings goals stay outside this comparison and are stated on screen. Bill alerts remain questions backed by source transactions; they never change money.
Section 7 owner decisions (2026-11-04): NF-7C migration is excluded. NF-7G uses FIFO cash age with unknown opening dates and a read-only posting-date spending calendar.
NF-7D now shares matching across search, scoped pickers and history. Windows/Linux native and frozen matcher probes passed in run 41922182521. Android packaged validation remains held by the owner’s unchanged selected-action policy; no release is published.
