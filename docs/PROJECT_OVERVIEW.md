# Lightning — Project Overview

**Last updated 2026-10-10 · app 1.0.0-beta.1.**

This file tells the story: what Lightning is, who it is for, what it answers and where it goes next. [Architecture](ARCHITECTURE.md) holds the technical side. The [Brand guideline](../guideline/) (`app.html`, `website.html`, `phone.html`) holds the visual side. The [Glossary](GLOSSARY.md) defines every term and figure. Shipped changes go in `CHANGELOG.md`; the hand-off is in `NOW.md`.

## Contents

Read only the section your task needs (`grep -n '^## ' docs/PROJECT_OVERVIEW.md`, then read from that line). The hand-off between the AIs is in [`NOW.md`](../NOW.md), not here.

| Section | Read it when |
|---|---|
| What Lightning is | You are new to the product |
| Product decisions that must hold | You change any figure, rule or flow |
| What you can do today | You need the current feature list |
| Period and fixed-horizon visuals | You change a chart, card or the period picker |
| The questions Lightning answers | You change what a screen answers, or a known gap |
| Reference workflow: a month with Mohab | You change Mohab's test or a screen he uses |
| Compared with the best budgeting apps | You plan a feature |
| UX plan (guideline 3.6) | You take a UX item, or answer the owner's open UX questions |
| Upcoming projects | You pick the next feature, or want to know which app an idea came from |
| Roadmap | You plan or finish a milestone |

## What Lightning is

Lightning is a local-first personal wealth app for Egyptians. It shows where your money is held, what it is invested in, how spending compares with your plan, and how what you own changes over time. The loop is simple: record or import activity, sort out unclear counterparties and categories, then read the analysis to spot patterns and save towards goals.

It keeps two questions apart: **where** value is held (an account such as CIB, the cash wallet, THNDR, gold at home) and **what** is held (EGP cash, COMI shares, fund units, gold grams, deposits).

Every number comes from one of three layers, and each screen says which:

- **Ledger — real money.** Posted transactions: where money actually came from and went.
- **Plan — what-if.** Budgets, reserves, scheduled bills and loans, sale factors and the cash forecast. It moves no money.
- **Report — reads both.** The Overview (the quick glance) and the reports under it: Budget, Investments, Expense analysis and Cash planning. They store nothing.

**Who it is for:** a busy user who won't read help text. Every figure has one name and one calculation everywhere, and a name that needs explaining gets renamed rather than explained. Every action gives visible feedback. A wrong or silent result is worse than an extra click.

**Priorities:** the simplest useful workflow with the fewest clicks; the same words everywhere; durable, searchable data; broad coverage of normal personal-finance cases. Calculations, matching, price processing and categorization are ordinary code, never AI calls.

## Product decisions that must hold

- **Work happens on `who/feature` branches** (owner, 2026-10-12). Every AI works on a branch named for who does it and what feature it builds (`claude/arabic-type-and-numbers`), never a random name, and merges finished work into `main`. The rule is [AGENTS.md](../AGENTS.md) section 6.
- **Arabic is for Egypt.** The app offers English and Egyptian Arabic for the same profile and the website links matching English and Arabic pages. Arabic pages read right to left; money, dates, currency codes and identifiers remain legible in their natural order. The [Glossary](GLOSSARY.md#العربية--المسرد-العربي) fixes the financial names used across both.
- **App feedback screenshots stay private.** The website allows up to five images per ticket; it stores them in the Apps Script deployment owner's private Drive folder and records the links beside the ticket in the feedback Sheet. The website repository owns the implementation and activation steps.
- **One ledger.** Account registers, the all-accounts view, budget actuals, investments, the Overview and the reports are all views of one transaction ledger.
- **Other people's money** (*Held for others*) stays in the account balance but belongs to its owner. It is left out of *What you own*. It is not income, spending or money owed to you.
- **Certain obligations count; forecasts never do.** Bills due and loans still to pay make up *What you owe*. Bills due come off Free cash, and What you owe comes off Net worth. Loans are payment schedules, not debt accounts. A loan payment counts as spending when it is paid. Credit cards, loan-interest accounting and money owed to you are out of scope; CD interest schedules are in scope as estimates.
- **Reserves are not budgets.** A reserve sets aside cash you already own and lowers Free cash. A budget limit changes only the spending plan. The two are never added together. The emergency fund is shown in months of *Average monthly income*, the same average the budget and the forecast use, unless Settings › Budget counts it in months of *Average monthly spending* (owner decision 2026-10-05: income is the default).
- **Categories describe the activity, not the direction of money.** Level 1 is Personal / Work / Investment / System Categories (loans, held money, internal transfers, capital allocation and adjustments), level 2 is broad, and level 3 is optional detail under an L2. Each category is + income, − expense or ± both; income is recurring (counted in the average and the forecast) or irregular, and an expense can be one-off (in cash flow, out of the budget). A category that has been used is archived, never deleted.
- **Names are canonical.** Similar spellings are suggestions the user must pick. Lightning never silently merges or creates a counterparty.
- **Physical gold** is tracked piece by piece: net gold weight per piece, karat and cost. It is valued at a price per gram for the same karat, and purity is never applied twice.
- **People see names, not codes.** Summaries round to whole pounds; inputs keep cents. Dates are ISO. Entry also accepts `31/1` and `31/1/2026`, Arabic-Indic digits, and sums in amount fields such as `120+35*2` (Glossary › Amount input).
- **Each visual says its time frame: the period you chose, or a fixed horizon.** Most charts and cards follow the period picker. Some keep a fixed horizon on purpose, because their question does not change with the period. Every section header names its frame. See *Period and fixed-horizon visuals* below.
- **Holdings value and Portfolio value are one figure** (2026-10-04): everything you own that is not cash, certificates and deposits included, on every tab and chart.
- **Every release stays downloadable** (2026-10-03): keep at least the three latest versioned downloads permanently. Each release gets its own immutable download and its own entry on the website. Never replace an older version's file or entry, and never remove an older release without the owner's say.
- **Free for 7 days, then a reminder, never a lock** (2026-10-04, the WinRAR route): the whole app works from the first minute with no card and no account. After 7 days it asks for a licence; it never blocks, hides or locks the user's data. Price not yet set. Why: a paywall before any try is Say's most repeated complaint ([Competition](COMPETITION.md)).
- **The website never mentions other apps** (2026-10-05): no comparison or "vs" pages, not even for search. Pages show what Lightning does, answered with Mohab's year (brand guideline B10, B11).
- **Each app fetches its own prices; the shared files are the backup** (2026-10-05): not daily by itself, but at least every month-end (month-end closes drive revaluation): opening the app after a month ends fetches that month-end's close, and Update prices fetches at any time. The daily collector keeps the shared price files as a backup a user can download if a source fails; typing a price always works and wins.
- **Price data is published only where its source allows it, and always cited** (2026-10-05; FX source changed 2026-10-07): the FX pack uses Banque Misr's dated public transfer buy/sell midpoint because CBE rejects the collector. It is labelled as a bank rate, not an official CBE rate. Stock and fund prices from TradingView, Yahoo or Mubasher are collected only to check sources, never published or shipped, until a licensed feed or a source's permission covers them. Each published pack names its source in its files and in the app.
- **Local only.** Data lives on the user's computer and is never committed to Git. The desktop app keeps each profile encrypted under Documents/Lightning, opened by a password of any length. A 12-digit recovery key and a security question together reset it. One thing opens a profile; two things change its password, question or key, and an open profile counts as one (owner decision 2026-10-05; Architecture › Encryption).
- **Planned multiple devices · phone as home.** One Lightning codebase will run on PC and Android. The phone holds the accepted encrypted ledger and edits it at home; one paired PC or laptop at a time may borrow a local working copy and keep editing if the phone goes quiet. Pair once, then use a short local handoff. Prefetch while the PC password is typed. The target is seconds, to be measured on a real phone. A future server or cloud copy is outside version 1.
- **Planned lend safety.** While a PC borrows, it saves locally and sends the phone an encrypted recovery copy about every three minutes when reachable and changed. Closing near the phone hands back; closing away saves a sealed copy and keeps the lend for later hand-back. The phone runs a user-started service during the lend and later reminders, never silently takes writing rights back. Copies stay local; cloud backup may be an explicit later opt-in.
- **Planned hand-back acceptance.** A locked phone may receive an encrypted return; it accepts it only after unlock, full verification and durable promotion. Until then the PC remains read-only. The integrated [implementation plan](proposals/multiple_devices.md#15-implementation-work-packages) divides the full cycle into 24 work packages with explicit dependencies, smaller subtasks, reading guides and exit checks; no sync implementation is claimed.
- **Planned: edit anywhere, one home confirms (owner-requested revision, 2026-10-07).** Every paired device saves edits locally; one stable home validates and confirms them. Opening a PC no longer moves writing rights. Pending changes appear immediately but stay out of reports until confirmed. Devices exchange small encrypted proposals and confirmed results, with whole copies for pairing or recovery. Keep strong one-time pairing, background phone sync using Android Keystore, home-only review, the home's compatibility policy, and deliberate home replacement with two owner secrets. The Cloudflare mailbox carries sealed messages; Firebase wake-up is best effort. Lost-home recovery names its surviving checkpoint and possible missing work; it cannot instantly fence an offline old home. This supersedes the automatic-lending proposal, and replaces the version 1 model above only after cutover. Building remains unscheduled; protocol, retention and acceptance: [edit journal](proposals/edit_journal.md).
- **Planned multiple devices, what you will see.**
  - Open Lightning on the phone, then on the PC. While you type the PC password, the copy arrives, and the PC opens ready to edit.
  - The phone shows "Lent to Office PC · read only".
  - Work on the PC with or without the phone nearby.
  - Close the PC near the phone and the ledger goes home. Close it away from the phone and it waits, safely saved, for the next meeting; the phone reminds you.
  - Next time you unlock the phone, it checks the returned copy, then reads the bank SMS that arrived meanwhile.
  - Without the phone, the PC can still show a dated, read-only saved copy for analysis.
  - Sometimes, for example after Android closed the app, the phone asks for its password before lending, and says why.
- **Two levels, few settings** (owner, 2026-10-06; Architecture › UI contract, *Two levels*): six sections, at most five tabs each, never a third level; a tab's settings behind its gear; a default before a setting; icons for row actions; one choice, one field; no line describing what its label already says. Tracking suggestions and the carryover start month become defaults.
- **Planned phone layout (owner, 2026-10-06).** The phone gets its own design and its own brand guideline, Part C of the brand guideline (3.25, 2026-10-06, drafted for the owner's review): a phone layout does not work on the PC, nor the PC's on the phone. Same pages' figures and services underneath. On the owner's phone (task 04c) the PC pages work but read as a squeezed desktop.
- **The phone: words, one tap to add, a short Overview (owner, 2026-10-07; guideline 3.27, Part C).** Every icon has its word beside it; an icon stands alone only when universal (search, back, add, ⋯, settings, hide amounts). Tabs inside a section are words, four as two rows of two. The add button is on every section's first page and on an account. The phone Overview is one screen: Get set up, Needs you, four tiles, Your position; the rest is one row each that opens in place. Why: Competition › Phone flow, words and icons.
- **Fewer steps to set up (owner, 2026-10-06).** The recovery key is shown once and confirmed with a press, not typed back. A profile has one password on every device: a PC that borrows it opens it with the same password as the phone.
- **Order to Google Play (owner, 2026-10-06).** Standalone Android is not enough. Milestone 1: phone and PC connected (pair, lend, edit, hand back), tasks 05–16c. Milestone 2: daily recording on the phone in its own layout, tasks 16d–19c. Milestone 3: bank SMS parsed into the ledger, tasks 21–22. Then the beta (23–24) and Google Play. The owner reviews at each milestone, not between.
- **Planned bank SMS.** The phone reads bank SMS only after the ledger has been accepted home and unlocked, including messages received during a lend. Known formats follow the import and category rules; unclear ones wait for review and later bank CSVs must not duplicate them. Learn formats bank by bank from sanitized examples. The full design and its limits are in [Multiple devices](proposals/multiple_devices.md).

## What you can do today

- **Accounts and ledger:** open an account with a starting balance; record money in, money out and internal transfers between your accounts; edit, void and restore, bulk select, search, and check an account against the balance the bank shows: a small difference (up to 1% or 100, whichever is larger) becomes one balance adjustment counted as Other spending or Other income; a bigger one is reviewed row by row or reimported. **System Categories** contains loans, held money, Internal transfers, Capital allocation and the editable Adjustment catch-all.
- **CSV import:** stage a bank CSV with one signed column or separate in/out columns. Only rows that need a decision need attention; a new name typed on several rows is created once; duplicates are flagged.
- **Budget:** Planned, Spent, then Left in plan. Each category takes one *Amount or %* field (`1,500`, or `12%` of average monthly income), or the average of recent months, with optional carryover. Views cover All time, YTD, Monthly and Custom. Scheduled loan payments, bills and subscriptions are planned in their category automatically until you set your own amount. The plan must leave your savings target (Financial health › Savings rate limit), or more when dated goals and the emergency fund's top-up (its gap to six months over two years) need it: the budget, Needs you and Financial health say so with the amount to cut, from one check. Saving the savings target or a goal says what it does to Most you can plan. Until a month has income, the salary set up in Recurring stands in for Average monthly income. Needs you names a category planned below the bills scheduled in it, a goal the plan cannot reach by its date (with the month it can), a raise in Recurring (plan with it, save the difference, or keep the average), a month that saved less than the target, and a category over plan two months running (move room to it from one that had room, in one step).
- **Cash planning (Plan · Recurring · Loans · Reserves):** *Safe to spend* until the next income (it keeps back the budget left and what you mean to save: goals, the emergency fund's top-up and the rest of your savings target), What you owe, the next 30 days and a three-month forecast. It also holds recurring bills, subscriptions and income (suggested from history, never created on their own), loans with progress and payoff date, and reserves with the emergency fund; each dated goal says what it needs a month, the same Saving for goals the budget and forecast count, and the emergency fund its monthly top-up. Saving a bill, subscription or loan says where Fixed costs and Loan payments to income now stand against your limits; *Fill this month* stops at Most you can plan. Loans leads with Debt to net worth, Debt to cash and Loan payments to income; Recurring with Fixed costs to income. A strict unique payment match settles automatically; an early or changed-amount payment is suggested for confirmation. The forecast separately shows estimated CD interest and maturity cash without calling returned principal income.
- **Financial health:** named figures with their periods, supporting amounts and profile-owned limits. Savings rate uses the last completed month; balances have an explicit as-of date; six completed months of Savings rate and Net worth are available under “Over time”. Limits only compare figures and do not change the ledger or plans. Emergency fund uses the same read-only target and income-or-spending basis as Reserves. Planned savings rate compares this month's budget with the same savings limit.
- **Certificates and time deposits:** a bank's `DEPOSIT` account is its CD portfolio; its Institution field identifies the bank and the portfolio cannot hold cash. Each CD is a separate non-cash `DEPOSIT.CD` asset with its own name, principal, rate, simple/compound method, payout/capitalization frequency, earliest withdrawal date, and maturity date. Enter maturity directly or enter a term in years; the date is calculated from the purchase date. Buying it creates a `BUY` transaction funded from a bank/cash account the user chooses, with sufficient owned cash checked on the purchase date. Interest and maturity proceeds are forecast estimates only: Lightning never posts interest automatically. Record actual interest manually from the bank statement; enter actual principal proceeds when redeeming. Old account-level CD terms are preserved and shown as legacy, not automatically converted, and cash in old `DEPOSIT` accounts must be moved out.
- **Investments:** buy, sell and dividends inside the brokerage account; prices fetched online (Update prices; and by itself on the first open after a month ends, for the month-end closes), typed in, or filled from the shared price files of the markets you follow (Settings › Price files; each held month-end and the latest close, a typed price wins). The app also fills from the files it came with on first run, each new month and after a brokerage statement import; Needs you lists any month-end price still missing; the period's *Net gain or loss* (Gain from sales + Price change on what you hold + Dividends and interest) alongside current holdings and *Holdings after sale (estimate)*.
- **Overview:** Needs you at the top (a closed row that opens into the list): the one review inbox, with every statement waiting for review and every transaction still without a category beside bills due, prices and plans, then your position: Net worth, Free cash, *What it is made of* and *If you sold today (estimate)* with a sale factor per class. Below that come Cash flow with the savings rate, Where it went, Investments at a glance, and Month by month as a closed row. Birdview was folded in on 2026-09-30, and `/birdview` redirects here.
- **Held for others:** money and units you hold for someone else. Account headers show *In this account · What you own · Held for others*.
- **Cash ownership:** from an account register, reassign cash between yourself and a saved person without changing gross account cash, or record an expense paid externally on your behalf. The latter remains an owned expense for budget and spending reports while attributing the same cash share to the payer.
- **Find and type faster:** Ctrl-K (or Search in the sidebar) finds a page, an action, an account, a counterparty, a category, an investment, a #tag or a transaction reference, and offers to search transactions. Amount fields take sums (`120+35*2`). A #tag in a note gathers its transactions with their Money in and Money out. The eye beside Search blurs every amount on screen.
- **Every page:** months are picked from a month picker, never typed. Up to three key notes under the title give the page's answer in one sentence, and one set of charts follows the brand guideline.
- **Version 1.0 beta:** the paired Windows ZIP and signed Android APK are published together from one tested commit. `Lightning.exe` needs no Python; the phone and PC hand one encrypted ledger between them over local Wi-Fi, with one writer at a time. Named profiles open with a password, recovery key and security question. Ordinary Windows recovery/fault acceptance and legacy import remain open; beta testers may use sample or real data with an independent backup.
- **Samples:** `python -m lightning --demo` opens Mohab's last three months in a separate database. An empty profile's welcome page can load Mohab's full 2026 CSV sample or one of four fictional Egyptian stories—Amr, Abdelrahman, Menna and Fatma—with distinct cash-flow, investing, freelance-income and emergency-reserve cases.

## Period and fixed-horizon visuals

The period picker (All time · YTD · Monthly · Custom) changes what most visuals show. A few keep a fixed horizon, because their question is about a set stretch of time, or about today. Each section header says which applies (for example "2026-09-01 to 2026-09-30", "Last 6 months", "Year to date" or "Today").

| Follows the period you chose | Keeps a fixed horizon |
|---|---|
| **Overview:** the four stat cards; Cash flow (net flow, column waterfall, Sankey); the Investments section | **Overview:** Net worth over time (the last 12 month ends); the position cards (as of today) |
| **Budget:** the savings waffle, the plan bar and Spent of plan | **Budget:** plans are monthly, so a longer period adds up its months |
| **Investments:** the saved-and-invested waffle; Net gain or loss with Growth; the allocation donut and biggest holdings (as of the period's end); money and value by class | **Investments:** the Portfolio value sparkline (always the last six months); Dividends collected (year to date); XIRR (since the first investment, shown after a full year); the horizon bar (today) |
| **Expense analysis:** the four KPI cards; the treemap; now against usual; daily calendar for short periods and monthly summaries for longer periods | **Expense analysis:** "usual" is the six whole months before the period; the usual range, small multiples and heatmap history use the 12 whole months before it |
| — | **Holding page:** the holding's whole history, up to 24 month ends; sparklines for the last six |

A sparkline never follows the period. It is a quick "where is this heading" beside a number, so it always covers the last six months. A comparison ("against your usual month", "usual range") always looks at whole months *before* the period, so the period never compares with itself.

## The questions Lightning answers

Each tab answers one main question first, then its natural follow-ups. **Partial** and **Missing** mark the gaps.

**What Mohab's test should do.** `tests/test_mohab_year.py` is the acceptance check for every question here. Mohab (below) is a real Egyptian salaried user, and the test judges Lightning the way he would, in the Windows WebView2 app:

- **Right answers:** every figure reconciles across tabs and stays right after a year of real life.
- **Usability:** each question is answered by starting at the Overview and clicking through. The route is checked; a dead end, a missing way back or a lost half-done task fails.
- **Efficiency:** it counts his effort. One typed bank balance, not clearing lines one by one; one fix, not one per row; nothing typed twice.
- **Speed:** pages must feel instant on an ordinary, encrypted PC. Long periods stay summarised (months, not 365 days) and pages stay light.
- **Simplicity:** the fewest controls that do the job; no placeholder text to delete; nothing that needs a manual.
- **Clarity:** plain words and readable numbers (no "System", no −1,351.7%), the date or period of every figure, and a warning when a plan cannot work.
- **UI:** compact rows, readable messages, and layouts that fit the app window and a phone.

User feedback becomes steps Mohab takes: fixed points are checked as answers, and each remaining gap is named plainly. Speed and look are also judged on a real PC, because the test sees only what the screens show.

| Screen | Main question | Leads with |
|---|---|---|
| Overview | Where do I stand, and what needs me? | Needs you, Net worth (What you own when nothing is owed), Free cash, what it is made of, cash flow, investments |
| Expense analysis | Where did my money go? | Money out, ranked categories, change from last period |
| Budget | Am I on plan? | Left in plan, categories over plan |
| Investments | What do I hold, and how did it do? | Net gain or loss for the period, holdings, allocation |
| Cash planning | How much can I actually spend? | Safe to spend, What you owe, the forecast |
| Reserves | Am I safe if something goes wrong? | Emergency fund in months of income, or of spending |
| Financial health | How do my named figures compare with my limits? | Emergency fund, Savings rate, debt and fixed-cost ratios; six completed months of trends |
| Account | What happened here? | One balance, then add/import and the register |
| Held for others | Whose money am I holding? | Balances by person |
| Settings · Checks | Is my data right? | Configuration and integrity checks |

**1. Where do I stand?**

| Follow-up | Answered by | Status |
|---|---|---|
| How does it add up? | Overview › Net worth rows and What it is made of | Answered |
| What part is not mine? | Held for others; account headers | Answered |
| What do I owe? | Overview › What you owe; Cash planning › Plan, Loans | Answered |
| Did it grow this period? | Overview › Change in what you own | Answered |
| *Why* did it change: saving, prices or new money? | No wealth bridge yet | Partial (M3.2) |
| How has it moved over the year? | Overview › Net worth over time (last 12 month ends) | Answered; wealth-change bridge is still partial (M3.2) |

**2. How much can I spend?**

| Follow-up | Answered by | Status |
|---|---|---|
| Why is it lower than my bank balance? | Free cash = Cash you own − Reserves − Bills due, each part expandable | Answered |
| How much until payday? | Cash planning › Safe to spend | Answered |
| What is due next? | Overview › Needs you; Cash planning › Next 30 days | Answered |
| Will I run short? | Cash forecast with its lowest point; Overview warns | Answered (3 months fixed) |
| Is my salary late? | — | Left out by decision |
| Can I afford this purchase now? | Safe to spend, before and after a new reserve | Partial: no "what if I buy it" check |
| Does an early payday count twice? | Recurring shows a plausible early payment; once Mohab confirms it, the January plan is settled and the average attributes it to January, while the bank-date cash-flow report stays unchanged | Answered with confirmation (Mohab step 18) |
| I have no salary this month: how long until the next one? | Safe to spend until the next scheduled income | Answered (Mohab step 27) |

**3. Where did my money go?**

| Follow-up | Answered by | Status |
|---|---|---|
| Which categories, and which transactions? | Overview › Where it went; Expense analysis bars drill down to transactions | Answered |
| More or less than last month? | Expense analysis › change from the comparable period | Answered |
| How much did I keep? | Savings rate (Net flow ÷ Money in) | Answered |
| What do subscriptions cost a year? | Cash planning › Recurring | Answered |
| A merchant or a few categories I care about? | No saved watchlist | Missing |
| A refund came back: did my spending go down? | It reduces the category in the month the refund arrives, not the month of the purchase | Partial (Mohab step 13) |
| How much did I spend on work that my employer owes me back? | Work categories; the reimbursement is a refund in the same category | Partial: nothing lists what is still unreimbursed |
| How much went in fees and bank charges this year? | Expense analysis › Fees & Charges, YTD | Answered |

**4. Am I sticking to my plan?**

| Follow-up | Answered by | Status |
|---|---|---|
| Which categories are over? | Budget meters, over plan first; Overview | Answered |
| How much of my income does the plan take? | Spent and Planned as % of Average monthly income | Answered |
| Is my loan in the plan? | "Includes … of loan payments scheduled this month" | Answered |
| What about next month? | Rules repeat; a future month cannot be opened yet | Partial |
| Where should the rest of my income go? | No "ready to assign" view | Missing |
| Rent went up, or I got a raise: does the plan follow? | A changed amount prompts Mohab to confirm the payment, choose the future planned amount and review any reserve target; neither plan nor reserve changes silently | Answered with confirmation (Mohab steps 20, 24) |
| What should I set aside for yearly bills (car licence, insurance, school fees)? | A reserve with a due date; Saving for goals spreads it over the months left | Answered (Mohab step 19) |
| Have I actually set it aside? | The goal's assigned cash, which moves only when he assigns it | Partial: nothing asks him to assign the monthly amount |

**5. How are my investments doing?**

| Follow-up | Answered by | Status |
|---|---|---|
| Which class or holding did best? | Net gain or loss by asset class; biggest movers | Answered |
| How much did I put in? | Money added | Answered |
| What would I get if I sold? | Investments › Holdings after sale; Overview › If you sold today | Answered |
| Am I on my target mix? | Investments › Set target allocation | Answered |
| Why does a holding show no gain? | No price yet: valued at cost and flagged | Answered |
| What did I make when I sold? | Gain from sales, after fees | Answered |
| When does my certificate mature, and what then? | The bank's CD portfolio lists each certificate's terms and maturity; Cash planning shows estimated interest and principal proceeds. The user records statement interest and actual redemption proceeds | Partial: legacy account-level terms are not converted, and no automated bank reconciliation |
| How are my dollar savings doing? | Currencies tab: native balance, translated value and month-end FX movement | Foreign cash supported; conversions and foreign securities still planned |

**6. Am I safe if something goes wrong?** The emergency fund shows months covered. Saving for goals shows what to set aside each month. Loans show payments made, what is left and the last payment; a skipped payment moves to the end of the loan.

| Follow-up | Answered by | Status |
|---|---|---|
| How long could I live if I lost my job? | Emergency fund in months of Average monthly income, or of Average monthly spending (Settings › Budget) | Answered (Mohab reads both after his job ends) |
| I paid for a repair from the emergency fund: what now? | The fund shows what is left; Free cash is unchanged | Partial: nothing reminds him to refill it (Mohab step 14) |
| When is the car loan paid off? | Loans › last payment | Answered |
| Can I pay the loan off early? | — | Missing: no early payoff or lump-sum payment |
| Is my debt under control? | Loans › Debt to net worth, Debt to cash, Loan payments to income: one KPI card each, with the two amounts divided | Answered (Mohab, 2026-09-30) |
| How much of my income is already promised? | Recurring › Fixed costs to income (bills, subscriptions and loans a month) | Answered (Mohab, 2026-09-30) |


**7. Is my data right?** Type the balance the bank shows and settle a small difference with one adjustment, review imports for gaps and duplicates, and run Checks. There is no stale-price warning yet (partial).

**8. What changes when my pay changes?** A salaried user's pay is not one flat number: raises, a yearly bonus or profit share, a 13th month, Ramadan and Eid grants, and paydays moved early for holidays.

| Follow-up | Answered by | Status |
|---|---|---|
| Where did my bonus go? | Money in › Bonus; Expense analysis for the same period | Answered |
| Does a bonus change my budget? | `BudgetService.income_average` excludes `EXP.WORK.BONUS` by default; a bonus does not lift Average monthly income | Answered; Mohab step 17's average is instead affected by January salary booked in December (step 18) |
| I changed jobs: what happens to my income figures? | Stop the old salary (its history stays) and add the new one | End-of-service pay is irregular and excluded by default; the no-pay-month average still skips zero-income months (Mohab step 27) |
| Was I paid my raise? | The account register shows the new amount; Cash planning › Recurring keeps the scheduled payment Due until he links it by hand | Partial |

Money held for others is left out of every owned, budget and performance view. Transfers are never income or spending. Refunds reduce spending in their original category.

## Reference workflow: a month with Mohab

The acceptance persona is **Mohab**, 31, salaried, in Cairo. He earns 45,000 EGP a month from ACME Egypt, paid into CIB. He has a CIB payroll account, a cash wallet and Vodafone Cash; an NBE 3-year certificate; and a THNDR account with COMI, Fawry and a money market fund. His gold is an L'Azurde ring bought by card and a gold pound from his grandmother. He holds 10,000 EGP of his mother's money in CIB. He pays rent, internet, phone and electricity monthly, and has a 24-month car loan.

Drive it in a browser through the screens only, and re-run it after any workflow change. The numbers must still reconcile. The demo household is the same month, dated to today.

| # | Step | Layer | What must be true afterwards |
|---|---|---|---|
| 1 | Open six accounts, typing dates as `1/7` | Ledger | Dates become `2026-07-01`; the sidebar shows **In your accounts** |
| 2 | Import three months of CIB (40 rows) | Ledger | 39 posted, 1 skipped; salary, rent, groceries and transfers categorized; Mom's 10,000 is **Held for others** |
| 3 | Move money to THNDR; buy COMI and Fawry with fees; buy a money market fund | Ledger | Holdings and brokerage cash show on Investments |
| 4 | Record the ring bought by card and the inherited gold pound | Ledger | Ring paid from CIB; the pound needs no cash account |
| 5 | Record cash and Vodafone Cash spending | Ledger | Each shows in Money out and in its category |
| 6 | Enter month-end prices | Ledger | Holdings value and Net gain or loss update |
| 7 | Set a 20,000 emergency fund and create the budget | Plan | Free cash = Cash you own − Reserves − Bills due |
| 8 | Track suggested recurring items; add electricity and the car loan | Plan | September's payments matched; What you owe = 60,000; the loan is in the budget |
| 9 | On 2026-10-06 mark salary, rent and a loan payment paid from the Overview | Plan → Ledger | Each posts a real transaction; Net worth moves only by the salary (+45,000); loans still to pay 57,500 |
| 10 | Read every tab | Report | Free cash and What you own read the same everywhere; Checks pass |

**The rest of Mohab's year.** Steps 1–10 are one ordinary month. Steps 11–31 carry the same household from October 2026 to September 2027 through what a salaried year brings: fees, a refund, a repair, a bonus, an early payday, a raise, Eid, installments, a share sale, a rent rise, a holiday, and a job change with a month between jobs. Every month also has the routine: salary on the 1st, rent on the 3rd, the car loan on the 5th, groceries, phone, internet and electricity.

`tests/test_mohab_year.py` runs these steps through the screens, one test per step. When a screen gap is fixed, its assertion and the **Today** column below change together. Steps 1–10 are still driven in a browser.

| # | When | Step | What must be true afterwards | Today |
|---|---|---|---|---|
| 11 | Oct | An ordinary month | Every recurring payment and the loan settle themselves; nothing is due at month end | Answered |
| 12 | 10 Oct | Withdraws 2,000 at a CIB ATM, with a 25 fee | Net worth moves by −25 only; the fee is in Fees & Charges | Answered |
| 13 | 15 Oct | Returns August's 1,299 Amazon purchase | Shopping goes down by 1,299 | Partial: it goes down in October (October reads −1,299) and August keeps the purchase |
| 14 | 18 Oct | Pays a 6,500 car repair from the emergency fund | The fund drops to 13,500; Free cash is unchanged; cash drops by 6,500 | Answered; nothing reminds him to refill the fund |
| 15 | 20 Nov | Gets a 300 COMI dividend | Money in shows Dividends next to Salary; pay is unchanged | Answered |
| 16 | 10–22 Dec | Pays a 1,200 work Uber; ACME pays it back | Work spending for December is 0; the refund is not income | Answered |
| 17 | 20 Dec | ACME pays a 90,000 year-end bonus | Net worth +90,000; Average monthly income stays 45,000 | Answered after Mohab confirms the separately suggested early January salary; Bonus itself stays excluded |
| 18 | 24 Dec | January's salary comes before the holidays | It settles January's payment; January's forecast expects no more pay | Answered after Mohab confirms the early-pay suggestion; cash-flow reporting still uses 24 December |
| 19 | Jan–Apr | Plans 9,000 car insurance due 30 April, pays it from the goal | Saving for goals shows 2,250 a month | Answered; but no cash moves into the goal until he assigns it, and it cannot pay the bill until he does |
| 20 | 1 Feb | Raise to 50,000 | February settles after Mohab confirms the changed-amount suggestion; later payments are planned at 50,000 only after he chooses it; December stays paid at 45,000 | Answered with confirmation, not automatic plan changes; Needs you then offers the raise to the plan, and he keeps his plan and saves the 5,000 (target 28%) |
| 21 | 9–10 Mar | Eid: gives 3,000 in cash, receives 1,000 | Gifts & Donations and Gifts Received; gifts do not change the salary average | Answered; the rolling January–March salary average is 48,333.33 after January's 45,000 pay and two 50,000 pays |
| 22 | Mar | Buys a phone on 12 installments of 2,000 from 15 April | What you owe +24,000; each installment settles itself | Answered (as a loan; credit cards are out of scope); in April Needs you names Loan payments planned at 2,500, below both loans' 4,500, and he changes it |
| 23 | 20 Apr | Sells 75 of 150 COMI for 7,100 after a 25 fee; moves it to CIB | 75 left; Gain from sales after fees; April's Money in is only the salary | Answered |
| 24 | 3 Jun | Rent rises 10% to 13,200 | June settles; July onwards is planned at 13,200 after Mohab accepts the prompt; reserve target is reviewed separately | Answered with confirmation; neither future plan nor reserve changes silently; Needs you names Housing & Rent planned at 12,000, below the 13,200 rent, and he changes it |
| 25 | Jul–Aug | Sets aside 15,000 for a Sahel trip; spends 14,200 | 800 left in the goal | Answered |
| 26 | 31 Aug | Leaves ACME with 30,000 end of service; adds Valeo at 55,000 from 1 October | The old salary stops with its history; Average monthly income stays 50,000 | Right since Categories marks Bonus irregular |
| 27 | Sep | Between jobs, no pay | Next income is Valeo on 1 October; the average does not rise | Known gap: zero-income months are skipped by the average; the test checks non-increase, not zero-month inclusion |
| 28 | 30 Sep | Reads the year | Money in 651,300 and Money out 295,186; Change in what you own 357,364; loans still to pay 34,500; Checks pass; nothing is due | Answered, except *why* net worth changed (M3.2) |
| 29 | 30 Apr | Reads Safe to spend after raising his target | It keeps back the emergency top-up (11,521) and the rest of the 28% target (2,013) | Answered |
| 30 | May–Jul | Wants a 60,000 laptop by 30 June | Needs you: the plan leaves 23,302 a month, so July at the earliest, or set it aside from free cash; he sets it aside, and in July, past its date, completes it | Answered |
| 31 | 30 Sep | Moves Talabat to Food (feedback round) | Food is over plan in July and August; Needs you moves 500 from Shopping in one step | Answered |

**What users reported.** After the year’s answers are read, Mohab revisits `user feedback/user-feedback-batch-001.md`. The screen test now checks the nine named points: paid dividend amounts, emergency-target warning, a today-only position, monthly summaries for long periods, no category sign key, a saved monthly investing goal, total fund valuation, dated Other asset values, and multi-file CSV import. Loading speed, keeping scroll position, compact review rows, chart colours and register balance are not checked from the screens.

**Not scripted, because Lightning cannot record them yet:**

- **A gam'eya.** Example: 10 months of 5,000, with the 50,000 pot in month 4. The payments are commitments, and the pot is his own money back, not income. Lightning has no gam'eya type, and an inflow needs an income category.
- **The NBE certificate maturing.** Its portfolio forecasts interest and maturity proceeds; Mohab enters the actual principal redemption and statement interest manually. Forecasts never post ledger activity automatically.
- **Dollar savings.** This waits for M4.
- **Paying the car loan off early.** There is no lump-sum payment.
- **A payslip's deductions** (income tax, social insurance). These are left out: record net pay.

## Compared with the best budgeting apps

The reference apps are YNAB, Monarch, Copilot, Simplifi, Rocket Money, Lunch Money and Actual Budget. The Egyptian apps people actually install are Say, Qershnat, Masarifi, Masareef, Money Manager and Wallet; what their users love and hate, and Lightning's main edge over all of them (the whole of an Egyptian's money, with numbers you can trust), are in [Competition](COMPETITION.md).

**Already on par or adopted:**

- Recurring detection that suggests but never creates (Monarch, Rocket Money, Copilot).
- Upcoming bills with automatic paid-matching and undo (Monarch).
- A projected balance with its lowest point (Simplifi).
- The monthly amount a dated goal still needs (YNAB).
- Subscriptions totalled per year (Rocket Money).
- Loan progress and payoff date.
- Rollover budgets.
- Transfers, splits and refunds.
- Real investment returns, local gold and money held for others, which most budgeting apps lack.

**Still missing, most valuable first:**

| # | Missing | Best example | Why it matters here |
|---|---|---|---|
| 1 | Capture on the phone in seconds | Say (voice, SMS), Copilot, Monarch mobile | Cash and Vodafone Cash spending is forgotten unless logged on the spot. Say's users love exactly this; it is where Lightning loses today. Planned: [Multiple devices](proposals/multiple_devices.md) |
| 2 | Automatic transaction feed | Bank sync in Monarch, YNAB; bank SMS in Say, Qershnat | Import is the heaviest step. There is no Egyptian aggregator, so parsing bank SMS or e-statement PDFs and Excel files (Upcoming projects #17) is the cheaper route. Their users' complaint to avoid: SMS entries that miss or invent a spend, so every parsed message is reviewed before it posts |
| 3 | Learned categorization rules | Monarch, Copilot, Lunch Money, Actual Budget | Rules with conditions are built (Upcoming projects #5), and Settings › Rules suggests a rule from what you file (built 2026-10-12) |
| 4 | ~~One review inbox~~ Done 2026-10-05 | Monarch, Copilot "to review" | Needs you now lists every waiting statement and uncategorized activity; recurring suggestions wait for the owner's answer |
| 5 | Reminders | Monarch, Rocket Money, Simplifi | A user who doesn't open the app never sees a due bill |
| 6 | Multi-currency | Lunch Money, YNAB, Wallet | Many Egyptians keep USD savings or earn USD. Upcoming projects #15 (FX revaluation) and #16 (US stocks) |
| 7 | Spending history | Monarch | Answers "am I improving?" |
| 8 | Give every pound a job | YNAB "Ready to assign" | Closes question 4's last follow-up |
| 9 | Watchlists | Simplifi | Track one habit without a full budget |
| 10 | Shared household | Monarch partner access | Couples manage money together |
| 11 | Guided first setup | Monarch, YNAB onboarding | Mohab's first run needed six account forms before seeing anything. The first run is also where Say loses users, to a paywall: Lightning's is 7 days free, never a lock (*Product decisions*) |
| 12 | Receipts and attachments | Monarch, Lunch Money | Warranty and gold purchase receipts |

**Known finance gaps** (the early-pay, raise and rent paths now require explicit confirmation; no-pay-month averaging in step 27 only has a non-increase assertion):


- **Left open by the 2026-10-05 audit** (its other wrong numbers are fixed, `tests/test_audit_numbers.py`): a payment scheduled on the 31st moves to the 30th after a shorter month and stays there.
- **Unconfirmed early salary** remains in the bank-posting month of the income average and may leave a future salary payment due. The Recurring tab suggests the plausible match; Mohab must confirm the specific transaction before the scheduled-month average and forecast adjust.
- **A changed recurring amount** prompts a future-plan update and a reserve review, but the user must choose them. A reserve is named only when the payment is explicitly linked to it; a name or category match does not silently change cash assignments.
- **CD projections** use an actual/365 day-count estimate, not a bank guarantee. Interest is never posted automatically. Existing account-level `cd_terms` stay visible as legacy and are not automatically converted. Cash in old `DEPOSIT` accounts must be moved out; these legacy terms remain pending a safe conversion workflow. Interest recorded from the certificate's bank counts as the certificate's return (Architecture › Investment return); it is not yet reconciled against the projection.

Bank sync and bill negotiation are not adopted. Any sync first needs a provider and regional coverage; local CSV stays the foundation. A "safe to spend" figure must always say which obligations and income it includes. Simplifi's projection, which leaves out planned spending, shows why.

## UX plan (guideline 3.6)

From a full UX review on 2026-10-03: Mohab's year at a 1,366 × 768 window (the PC app), every screen checked against Brand guideline 3.6 Part A. The structure is two levels since 2026-10-06 (Architecture › UI contract, *Two levels*). Batch 1 is done; the rest is ranked by what a real user meets first.

**The user's route.** A salaried user opens Lightning to answer, in order: *Where do I start?* → *Is my money in?* → *How much can I spend before payday?* → *What is due?* → *Am I on plan?* → *Where did it go?* → *How are my investments?* → *Is my data right?* Each tab answers one of these first; the Overview's Needs you is the to-do list across them.

**Done in batch 1:** KPI cards coloured by meaning with an icon tile; Needs you words ("Personal over plan", "Sahel trip is past its date"); an "Over plan" card instead of a negative "Left in plan"; no impossible savings rates (−1,375.2% becomes "—" with the gap in words); four, then Other in donuts, the Sankey, treemaps, bars and small multiples; section headers carry only the title and dates; trend month labels no longer overlap; money out in ink and transfers unsigned in registers; soft field wells; Nile sub-tabs; no all caps; the register's balance no longer clipped at 1,366px; budget spent in soft rose; a Back route on transaction, holding, planner and prices pages; Accounts calls its total What you own.

**Next, by impact:**

1. ~~**First run.**~~ Done 2026-10-03: a "Get set up" card on the Overview until five steps are done; the welcome lists certificates and uses real icons; a new bank account leads with Import a statement; Plan shows an empty state instead of a forecast from no income.
2. ~~**Import review, one decision per name.**~~ Done 2026-10-03: one choice per imported name with its rows collapsed under it (Mohab answers 17 names instead of 43 rows; the 300-row statement is 287 KB instead of 2.2 MB); "Discard this import"; Import CSV offers to continue or discard a waiting review. Still open: the button says "Post ready rows" while undecided rows post as Unaccounted.
3. ~~**The category picker.**~~ Done 2026-10-03: focus lists every choice under its L1 header and selects the current text; the import starts on an empty "Choose a category".
4. ~~**Bulk edit.**~~ Done 2026-10-03: Set category for selected rows; transfers, investments and splits are skipped and counted. Still open: bulk counterparty.
5. ~~**One name, one number.**~~ Done 2026-10-06: Reserves says free cash in one line (the breakdown is on the Overview and Plan); the Overview has one donut and no column waterfall under the Net flow list; Plan shows loans still to pay once, with a By loan list only for two loans or more.
6. ~~**Registers as two-line rows.**~~ Done 2026-10-07: counterparty and amount, then category · account · date with the balance under the amount; no Action column; header figures in whole EGP.
7. ~~**Honest prices.**~~ Done 2026-10-03: Needs you says "Prices are out of date" (older than about two months) and links to Update prices; the holding page flags its own price.
8. ~~**Reserves table**~~ Done 2026-10-07: each reserve is a two-line row (name, kind and due date with its set-aside field; an Azure meter, what is left to fund and a status word) with Edit and payments underneath; the emergency fund says "13,500 left of 20,000 · 6,500 used" with Refill. A one-off reserve spent in full stays until its ✓ moves it to Completed.
9. ~~**Words and numbers sweep**~~ Done 2026-10-07: whole EGP on Accounts' totals, Held for others and a loan's amount borrowed; no internal codes on Prices or Sale factors; Data checks without "custody subledger"; "Add a counterparty"; a reserve's Repeat is a segment; Deactivate already uses the app's own dialog.
10. ~~**Tab-by-tab audit, 2026-10-06**~~ Done 2026-10-07 (Mohab's sample at 1,366px): Health redesigned; header settings buttons removed; squashed header icons; Holdings table cut off; each savings rate names its month; the emergency top-up is one figure (Budget, Plan, Reserves, Health); Recurring's share of income is its Fixed costs card only; Investments hides Money and value by class rows that are 0 and the horizon bar while every holding is unassigned; the forecast legend draws the forecast dashed; the current month ahead is "Rest of 2026-10"; Accounts balances in Azure; no "e.g. THNDR", no "›" on Counterparties' learned category; If you sold today says a certificate is locked until its date; "1 day"; the Planner tab is the one way to the planner, and it links to Target allocation. Sparse Spending charts and KPIs, close Plan dates, and certificate price posting and card widths are resolved.

**Owner decisions (2026-10-03):**

- Budget's low-confidence background estimates count in Left in plan, with a small "!" beside them that says they are low confidence and why.
- The Overview's Investments section shrinks to one row of figures with a link to the Investments tab.

**Still open (asked again in plainer words):**

- ~~*Recurring suggestions.*~~ Done 2026-10-06: Looks recurring no longer offers everyday spending (food, eating out, shopping, transport, entertainment: the budget's) or investment income (certificate interest, already in the forecast), and *Not recurring* hides a suggestion for good.

## Upcoming projects

Features worth building, each with the app it came from (added 2026-10-05). Unless marked Built, these are not started or scheduled; the owner picks what enters *Next* in [`NOW.md`](../NOW.md). The evidence is in [Competition](COMPETITION.md). The gaps already ranked in *Compared with the best budgeting apps* (phone capture, bank feed, reminders, multi-currency, household and the rest) are not repeated here. When one is built, its figures get one name in the [Glossary](GLOSSARY.md) and it moves to *What you can do today*.

**Asked for by the owner:**

| # | Project | Idea from | What it would do |
|---|---|---|---|
| 1 | **Return against the risk-free rate** (the risk premium) | **Quicken** (Growth of $10,000 against market indexes, and against a buy-and-hold alternative); **Monarch** (portfolio return against the S&P 500, time-weighted) | Beside each holding's and the portfolio's return, show what a risk-free Egyptian choice (a bank certificate or treasury-bill rate) would have paid over the same dates, and the difference: what Mohab gains, or loses, for taking risk. Neither app compares with a risk-free rate; in Egypt a certificate is the bar every investment must clear, so this is Lightning's own twist. Needs a dated rate history and a time-weighted return beside XIRR |
| 2 | **Arabic version** | **Say, Masarifi, Masrofi** (Arabic that works is praised); **Money Manager, Wallet** (lose Egyptian users for no Arabic, or for removing it); **Actual Budget** (translation scaffolding: string files, a CI job that extracts strings, a review rule that every visible string is translated) | Every screen in Arabic and right to left, numbers never mirrored, Hijri dates beside Gregorian (asked of Money Manager and Wallet). Add the scaffolding before more screens are written. Competition calls Arabic a launch condition for Egypt. The brand guideline has no Arabic or right-to-left rules yet: ask the owner before writing any |
| 3 | **Financial health** | **NetTrack** (a 0–100 score from savings rate, net-worth growth, debt-to-asset ratio, emergency runway and spending stability); **WalletHub** (WalletScore). From their store pages and a search summary; neither was tried | **Built 2026-10-05** as a read-only profile with existing Glossary figures, adjustable per-profile comparison limits, an Emergency fund target shared with Reserves, a dated balance view and six completed-month Savings rate and Net worth trends. No score or new financial calculation. Not built: debt to assets (debt to net worth says the same), housing to income (fixed costs include rent), and a combined score. |

**Asked for by the owner, second batch (2026-10-05):** the three belong together. Money in another currency needs a rate; a US stock needs both a price and a rate; PDF and Excel files are how most statements, and other apps' exports, arrive.

| # | Project | Idea from | What it would do |
|---|---|---|---|
| 15 | **Multi-currency and FX revaluation** (Roadmap M4; foreign cash built) | **Wallet** (loved for multi-currency; one user must re-enter changing rates by hand); **Lunch Money, YNAB** (native multi-currency); **Say, Qershnat** (multi-currency wallets) | Profiles register ISO or custom currencies, choose a base before monetary history, and give each account a currency. Foreign cash uses dated rates; the ledger preserves native and base amounts and monthly checkpoints separate FX movement from income and spending. Currencies shows native balances and translated values; missing rates are unavailable. Still planned: cross-currency conversions with sent/received amounts and spread, foreign securities, and automatic rate sourcing in the account workflow. |
| 16 | **US stocks** (Roadmap M4; needs #15) | **Monarch, Copilot** (US holdings and net worth); **Quicken, Banktivity** (return in both currencies) | Holdings listed on NYSE or Nasdaq, priced in USD, valued in EGP. A holding's return shows twice: in dollars, and in pounds, with the exchange part separated, so a dollar stock that rose 10% while the pound weakened is not shown as a pure stock gain. US prices come from the US price file (`docs/proposals/market_data.md`) |
| 17 | **Read PDF and Excel files** (Roadmap M7) | **Say** (reads invoices and bank SMS); **Masroofy** (scans receipts, imports bank messages); **Say's** reviewers (a Wallet user cannot move in); **Quicken, Monarch** (statement import) | Import bank statements as **PDF** (text statements first; scanned ones later and optional) and as **Excel** (`.xlsx`, `.xls`), through the same review as CSV: a column mapping remembered per bank, rows reviewed before anything posts, duplicates flagged. Also the way in for other apps' exports (#11). Reading is ordinary code, never an AI call. Today the PDF is refused and Excel is only written (the AI workbook), so this adds a reader with tighter limits than CSV: size caps, no macros, no formulas run, no external links followed, and nothing written to disk in plain text |

**Asked for by the owner, third batch (2026-10-10):** high priority: expand listed-equity coverage from EGX to Nasdaq and the major European and GCC markets, keeping prices, currencies and EGP valuation explicit.

| # | Project | Idea from | What it would do |
|---|---|---|---|
| 18 | **High priority: listed shares across the US, Europe and GCC** (Roadmap M4; builds on #15–16) | **Owner request** | Extend stock lookup, price history, holdings and investment returns beyond EGX. Cover Nasdaq-listed US shares; leading European exchanges (London Stock Exchange, Euronext, Deutsche Börse/Xetra, SIX Swiss Exchange and Nasdaq Nordic); and all six GCC markets (Saudi Tadawul, Abu Dhabi Securities Exchange, Dubai Financial Market, Qatar Stock Exchange, Boursa Kuwait, Bahrain Bourse and Muscat Stock Exchange). Keep exchange, identifier and trading currency explicit, value foreign holdings in the profile's base currency using FX, and verify data-source coverage and licensing before choosing providers. |

**From the Competition research** (the order follows Competition › Actual Budget code analysis › Suggested order, then the Egyptian apps):

| # | Project | Idea from | What it would do |
|---|---|---|---|
| 4 | **Undo and redo** | **Actual Budget** (20 steps over every change); Say and Masarifi users ask to edit and delete | Undo the last edit, delete or import, not only bulk rules and a skipped payment |
| 5 | **Rules with conditions** | **Actual Budget** (rules engine) | **Built 2026-10-06:** Settings › Rules (Glossary › Rule; Architecture › Default category for a counterparty). **Suggested rules built 2026-10-12** (Architecture › Default category for a counterparty). Still open: a rule that renames the counterparty |
| 6 | **Layered import match and a locked checked month** | **Actual Budget** | Match by bank reference first, then by amount and nearest date; a month checked against the bank is never overwritten by an import; merge two transactions. The same match serves SMS against CSV |
| 7 | **Weekend-aware schedules** | **Actual Budget** ("skip weekend", amount ranges) | **Built 2026-10-06:** a Friday or Saturday due date moves to Thursday or Sunday (Architecture › Cash planning contract); payments already match within an amount range. Still open: public holidays, from a dated list in the market data pack |
| 8 | **Fill this month** | **Actual Budget** (budget templates) | **Built 2026-10-05:** review base-limit proposals from last month or scheduled Bills and Subscriptions, or view reserve-goal needs separately; edit and apply selected amounts for this month only |
| 9 | **Entry helpers** | **Actual Budget** | **Built 2026-10-05**: sums in amount fields with powers and brackets (Glossary › Amount input); a Ctrl-K command bar, also Search in the sidebar; privacy mode, the eye in the sidebar, which blurs every amount (Glossary › Privacy mode); and #tags in notes (Glossary › Tag) |
| 10 | **Age of Money and a spending calendar** | **Actual Budget** (reports) | How long money rests before it is spent, for people who live salary to salary; a calendar of spending days; one saved filter shared by search, reports and rules |
| 11 | **Move in from another app** | **Say**'s reviews: a four-year Wallet user cannot bring their data, so cannot switch | Import the exports of Wallet, Money Manager and Masareef, mapping their categories once |
| 12 | **Deeper investments** | **Quicken, Banktivity, GnuCash, Moneydance** | Stock splits and bonus shares, reinvested dividends, return of capital, choosing which lot is sold, and a time-weighted return (#1 needs it too) |
| 13 | **Silver, property and vehicles** | **Qershnat** (has them); Say's users ask for "property, silver, watches" | Value them beside gold in What you own |
| 14 | **Gam'eya and zakat** | **Qershnat** (gam'eya with turns and proof of payment; its users ask for zakat); **Masroofy** (zakat) | Waits for the owner (`NOW.md`, question 3) |

**For the code** (from **Actual Budget**): one change note per change, joined at release, to end changelog conflicts between AIs; visual snapshots of key screens to guard the brand guideline; a warning on any push that touches a database migration.

## Roadmap

### Pre-ZIP release readiness

Verified UI fixes: Budget overlap at about 941px, the Cash planning tab strip and shared period pill at 390px, Settings data-card overflow, and account/all-transactions registers scrolling inside their cards. Holdings now uses five columns with expandable details, and the reviewed own-data fields have type-and-pick controls. Mohab's early salary, raise and rent scenarios pass with explicit confirmations; the CD terms and forecast mechanism is covered by focused tests. A full interactive click-through of every control and acceptance on an ordinary Windows PC remain outstanding before the ZIP release. No new ZIP is implied by these source changes.

| Milestone | State | Next |
|---|---|---|
| M0–M1 Foundation and cash accounts | Shipped | — |
| B Budget, B.1 Budget flow | Shipped / in progress | Change one category without the full grid; first-use flow |
| M2 Reports and corrections | Partial | Balance adjustments, month close |
| M3 Manual investments | Shipped | — |
| M3.1 Instrument catalogue | Partial | Coverage and identifier quality |
| M3.2 Wealth history | Partial | Wealth-change bridge; owned-only XIRR (net-worth trend is shipped) |
| M4 Market data and FX | Started | Price files per market and foreign cash accounts with manual dated FX and month-end FX reevaluation built. **High priority next:** expand listed shares from EGX to Nasdaq, leading European exchanges and all GCC markets (Upcoming project #18). Also planned: account currency conversion, foreign securities, and rate-pack use in the account workflow (#15, #16) |
| M6 Deposits and gold details | Partial | Bank-specific CD portfolios, per-certificate purchase/redemption ledger activity and forecast-only interest are built; next: ordinary-PC acceptance, legacy conversion, statement reconciliation, local gold costs and buyback |
| Physical gold items | In progress | Item purchase/sale and report integration |
| M7 Planning and imports | Partial | Shipped: CSV import, Cash planning, and linking statement rows to entries already recorded (no money counted twice). Next: reminders; reading PDF and Excel statements (Upcoming projects #17) |
| Search | Partial | One search for pages, actions, records and tags, on the Search page and the Ctrl-K command bar (2026-10-05). Next: scoped pickers, confirmed-alias history and measured ranking (Architecture › Search and identity contract) |
| Multiple devices | Milestones 1 and 2 built, in owner review: pair, borrow, edit, hand back, seal, take back; move a PC profile's home to the phone; the phone frame (Part C) with its own Overview, Accounts, account list, entry sheet, Budget, Cash planning, Investments and Devices | Owner review. Milestone 3 (bank SMS) started: CIB and NBE messages read by the phone itself (with permission), shared or pasted on From SMS, reviewed before posting; next Google Play's SMS declaration and more banks. Still open: discovery instead of typing the address, prefetch while the password is typed, periodic recovery copies, the two-PC fault gate, power-loss evidence. [Plan](proposals/multiple_devices.md#15-implementation-work-packages). |
| In-app updates (Windows) | Planned for later | An **Update** button: check `Lightning-downloads` for a newer version (on press, or an opt-in automatic check); download it, verify its signature (key kept outside GitHub), unpack beside the current app, then a small helper swaps folders and reopens, keeping the old one for rollback. Profiles in Documents/Lightning are never touched. Refuse while a lend or hand-back is unfinished. Evaluate Inno Setup or Velopack against a hand-made helper; a code-signing certificate is optional (it removes the unknown-publisher warning). Pairs with multiple devices task 19 (update compatibility). Android updates come from Google Play. |
| Paired apps (v1.0.0-beta.1) | Tester beta published | Tested Windows ZIP and signed Android APK from one commit, with direct one-writer handoff over local Wi-Fi. Encrypted profiles and restore are early previews; next: ordinary-PC recovery/fault acceptance, legacy import, native file pickers and unresolved-evidence repair. |

**Next up:** reminders.
