---
title: Outside review of every tab - one organism, fewer numbers, smarter links, less explaining
type: polish
area: product
status: ready
created: 2026-10-15
by: Claude
skills: bug-hunt
app_version: 1.1.0b1
commit: 08bb699
repo: app
---

## Report

**Brief from the owner:** look at every tab and button as an independent UX tester and brand strategist, not as a keeper of
the guideline. Say what is good, what looks odd, what can be linked or wired better, and what to build next. Design for
someone who is lazy and in a hurry. Do not fix anything. The companion report covers brokerages, exchanges and currencies:
[2026-10-15-investments-brokerage-multi-exchange-design.md](../5-investments/5G-brokerages-across-exchanges.md).

**How I looked.** Mohab's sample year (`python -m lightning --sample`, prices offline, today 2026-10-15) on main `08bb699`,
which includes designs 004 (institution pick list, first-run currencies, import review as rows). I crawled 734 pages
(61 page types), saved a full-page shot of each at 1440 px, read every page's text, and checked numbers against
`data/sample.db`. I opened forms but did not submit them. **Not covered:** the phone layout (`tools/phone_check.py`
fails in this container), Arabic, and first run on an empty profile.

---

### 1. The verdict

Lightning's engine is better than most paid apps: one ledger, honest estimates, gold by the gram, certificates, gam'eya,
zakat, custody, FX split, undo. What lets it down is the surface. **It feels like nine good apps sharing a sidebar.**
Each tab works out its own numbers, uses its own words for them and explains them in its own sentences. Someone in a hurry
sees a dozen figures that look alike, reads three sentences under each, and still can't tell which one to act on.

The fix is mostly taking things away and connecting what is left, not building more:

1. **Three hero numbers** across the app (Net worth, Spendable until payday, Left this month). Every other figure is a
   drill-down from one of them and has exactly one name.
2. **One home per thing.** Each page sits under one tab and keeps that tab's bar.
3. **Wire what the app already knows.** It often holds the answer and still asks the user (examples in §4).
4. **Expert settings leave everyday forms.** A form asks only what a lazy person must answer; the rest is inferred or kept
   behind *More*.
5. **Labels, not lectures.** A number gets a label. The explanation sits behind an (i) or in *Show the numbers*.

### 2. What is already good (keep it)

- **One ledger, everything derived.** Integrity checks pass 8/8 and figures reconcile to the cent (`/checks`). This is the moat.
- **Institution pick list (T7)** with Arabic search names, monograms and "Used before" grouping. This is the owner's
  example and it is already built. §5.1 takes it further.
- **The inline register row** (date, counterparty, category, amount, +) is the fastest entry in the app. Copy it everywhere.
- **Mark paid** on Cash planning and Needs you: one tap that does the right thing.
- **The price/FX split** on a foreign holding ("Price part +11,011 · FX part +2,206"). It is rare and valuable; show it bigger.
- **Holding page questions** ("Is it making money?", "How bumpy has it been?", "The journey"): good questions with charts that answer them.
- **Expense analysis** compares the same days of earlier months. That is honest and uncommon.
- **Cash planning's "From free cash to safe to spend" bridge** shows its working as a bar chart. Use this pattern
  everywhere two numbers differ.

### 3. Five problems that run through every tab

#### 3.1 Too many numbers for one pile of money

On one screen of the sample (2026-10-15) the user meets all of these:

| Name on screen | Value | Where |
|---|---|---|
| In your accounts | 602,179 | Sidebar, Transactions |
| Total balance | 602,179 | Accounts (same figure, second name) |
| What you own | 596,179 | Overview, Accounts |
| Net worth | 546,089 | Overview |
| Cash you own | 243,692 | Overview, Payday |
| Free cash | 208,602 | Overview, Cash planning, Payday ("Cash available to assign") |
| Safe to spend | 181,682 | Cash planning |
| If you sold today | 448,464 | Overview |
| Holdings value = Portfolio value | 352,486 | Overview, Investments (one figure, two names) |
| Holdings after sale | 239,862 | Overview, Investments |
| Left in plan | 32,010 | Overview KPI, Budget |
| Budget left to spend | 15,550 | Cash planning (a different figure from Left in plan) |
| Bills due | **15,090** on Overview, **12,590** on Cash planning › What you owe | same label, two values |
| Savings rate | **93.2%** Overview/Budget/Investments, **44.4%** Health | same label, two periods, no period shown beside it |

Every value is correct by its own rule. Together they mean nothing to a lazy user. Concrete fixes:

- **Bills due must be one figure.** The 2,500 overdue car-loan instalment counts under Bills due on the Overview and under
  Loans still to pay on Cash planning. Pick one rule. If both must stay, rename one ("Bills due, loans excluded").
- **Budget left to spend (15,550) vs Left in plan (32,010).** The first counts only the 17 days before payday and leaves out
  bills already counted. Rename it "Budget for the next 17 days" and link it to Budget.
- **Savings rate** always carries its period ("Savings rate · Oct so far"). Better still: in the first ten days of a month
  show last month's complete rate. 93.2% on day 15 because rent wasn't paid yet is flattering, not informative.
- **Retire one of each duplicate pair:** Total balance = In your accounts; Portfolio value = Holdings value; Free cash = Cash
  available to assign.
- **Promote three heroes.** Net worth (what I'm worth), Spendable until payday (what I can use), Left this month (am I on
  plan). The sidebar, Overview KPI row and phone home show only these. Everything else opens from them as a bridge (the
  Safe-to-spend bar chart pattern).

#### 3.2 The app explains instead of designing

Most cards have a subtitle that repeats the label or the method. Some examples:

- Accounts header: "Where is your money held?" Add an account: "An account is a place where money is held." Investments:
  "Valued as of 2026-10-15". New investment: "Something you can own units of: a stock, a fund, gold."
- Add account › Starting balance: two sentences, then "Leave blank if you own this starting balance." under *Held for*.
- Investment trade form: "Choose Buy, Sell, or Dividend. Units are always entered as a positive quantity." + "Fees (inside
  the amount)" + "Add fees on top instead" + "Leave fees at 0 when there were none." + "Enter the number of units bought.
  Fees are included in your cost basis." That is four instructions for one row of fields.
- Investment prices: a 60-word paragraph naming TradingView, Yahoo Finance and Mubasher. Users don't need sources unless
  something fails.
- Cash planning KPI cards: "Cash you own after reserves and bills due · today", "On top of your plan until 2026-11-01",
  "Cash at its lowest month end in the forecast". Then the forecast chart repeats "lowest 180,331 in 2026-11".
- Weekly review: "Work through the decisions below, then record your review. Recording a review never dismisses unresolved
  items." plus a checkbox: "I reviewed the remaining decisions. They stay visible until resolved."
- Account page: "By asset class · Level 2 · largest share first" (internal jargon), then "0.00 / 0.00% of held" columns
  when nothing is held for others.

**Rule to adopt:** a card carries its label, its number and at most one *changing* fact (a date, a delta, a status). Static
explanations go behind a small (i) that opens the Glossary sentence `lightning/core/figures.py` already holds. Empty
columns (held for others = 0) are hidden.

#### 3.3 Pages without a single home

| Page | Reached from | Tab bar it shows |
|---|---|---|
| Currencies (`/accounts/currencies`) | Overview › Currencies, Accounts › *Other currencies* button | Overview's (Summary, Spending, Health, Currencies) under an *Accounts* link |
| Review activity (`/activity`) | "Review activity" link on every register | Overview's tabs |
| Weekly review (`/review`) | Overview link | Overview's tabs, but Review is not one of them |
| Financial assets (`/investments/assets`) | Settings › Settings in each tab, Investments gear | Investments' tabs |
| Certificates (`/deposits/5`) | Sidebar *Deposits* group | Investments' tabs (Holdings, Planner, Prices) |
| Zakat | Settings switch says "a tab under Accounts" | - |
| Transactions | Accounts › Transactions | Accounts' tabs |

The user can't build a mental map when the same page shows a different bar depending on how they got there. And Settings
has a section called "Settings in each tab" just to list the gears. **Fix:** one sitemap (below), each page in exactly one
place, and one gear location: Settings links to the gears, never the reverse.

Proposed map (5 tabs, unchanged sidebar, contents regrouped):

```
Home      Overview · Needs you (with Weekly review inside it) · Spending · Health
Budget    This month · Fill / raise · Payday plan
Plan      Next 30 days · Recurring · Loans · Reserves · Forecast
Wealth    Holdings · Certificates · Gold · Planner · Currencies · Zakat
Accounts  Accounts · Transactions (one list; the Activity feed becomes a filter of it) · Held for others · Import
Settings  Your data · Categories · Names · Rules · Checks · Prices and markets · Financial assets
```

#### 3.4 The app holds the answer and still asks

These are the "smart links" the owner asked for. Every one of them is data Lightning already has.

1. **Certificate interest.** NBE pays 1,833.33 into CIB Payroll on the 15th of every month. The certificate expects
   1,868.49 or 1,808.22 on the 1st (day-count interest), so nothing matches. Needs you shows **nine** "Certificate interest
   needs review" items. The certificate page is 7,725 px tall because each of the nine lists all 20 incoming payments,
   salary included, with nothing pre-selected. **Wire:** match by payer (the portfolio's institution) and nearest date
   within a tolerance, pre-tick the obvious receipt, offer *Match all nine* once, and learn the bank's fixed monthly amount.
2. **Price files.** The user holds a Nasdaq ETF but *US stocks and ETFs* is unticked on Price files. Holding something
   should follow its market automatically.
3. **Emergency fund 0.6 months** on Health ("Below your limit") while cash you own covers about 8 months of spending.
   The ratio counts only the emergency reserve. Either show both ("0.6 months set aside · 8 months of cash") or count
   free cash with a lower weight. Today the most alarming number in the app is the least true one.
4. **"Held for" lists merchants.** The owner picker on Add account and Add holding offers Abou El Sid, Amazon, Barber,
   Bawab, ACME Egypt. People and businesses are one list. **Wire:** counterparties get a kind (person / business); owner
   pickers show people only.
5. **Brokerage cash in Safe to spend.** Cash you own (243,692) includes 21,016 sitting in two brokerages, one of them a
   US dollar account. That cash feeds Free cash and Safe to spend, so it tells Mohab he can spend money that is in another
   country. Payday says "Cash in another account or brokerage still needs a transfer", which shows the team knows. Make
   it a per-account switch, "Counts as spendable", off by default for brokerage, certificates and foreign currency.
6. **The account form ignores the institution's kind.** `institutions.csv` knows THNDR is a broker and Vodafone Cash a
   wallet, yet the Type field stays on "Bank account" until the user changes it. Picking the institution should set the
   type, the currency and the name ("CIB · EGP").
7. **Salary is called a bill.** The activity feed says "ACME Egypt · Work › Salary · Bill linked". The link is to a
   planned income. Say "Planned" or show the plan name.
8. **Recurring knows the salary went up** ("Recurring expects 54,167… 4,167 more than your average"), but the Budget
   page says nothing. A raise should prompt "Raise your plan or save the 4,167?" on Budget, where the decision is made.
9. **Overdue bills look the same as upcoming ones.** Landlord (due 10-03) shows the same "Due" chip as WE Internet (due
   10-20). Twelve days late deserves "Late · 12 days" and should sit first.
10. **Locked certificate in If you sold today.** The 100,000 locked certificate appears as a positive line, but
    448,464 = 208,602 + 239,862 leaves it out. Show it struck through or as "Not available until 2027-01-01".

#### 3.5 Expert settings sit in everyday forms

- **Add a loan** asks "Match transactions within N days", "Amount difference allowed %" and "On a weekend: Keep / Day
  before / Day after". Defaults are fine for 95% of people: hide them under *Matching*.
- **Add an account** puts *Held for* and *Notes* in the main form, and asks for the Name before the Institution and Type.
- **Every register** shows Search, yyyy-mm, Date period, Saved views, View name and Save view in two rows, with labels
  floating at different heights (`/accounts/1`, `/accounts/7`, `/transactions`). Saved views should be a single *Views*
  menu; *Save view* appears only after a filter is applied.
- **Trade form** asks for Units, Amount and Price per unit, then Fees and fee mode. Ask for Units and Total paid, then show
  "≈ 220.63 per unit" as a result. Fees stay optional, under one link.

### 4. Tab by tab

Each tab gets **Odd** (looks or reads wrong), **Cut** (redundant), **Link/Wire** (connect it) and **Next** (expansion).

#### 4.1 Shell and sidebar

- **Odd:** the sidebar header "Accounts · Balances in EGP" and the "In your accounts" line repeat what the Accounts page
  says. *Dollar brokerage* shows 114,211 with no hint that it is a USD account.
- **Cut:** the eye (privacy) button next to Search is easy to miss: make it a keyboard shortcut plus Settings, or keep
  it and give it a tooltip.
- **Link:** group names differ between screens: sidebar "Cash & bank / Deposits / Investments", the Type hint "Shown under
  Bank Balance", account groups "Liquid Cash / Physical Cash / Brokerage Cash / Other Investments". Use one set of words.
- **Next:** pin up to three accounts at the top. Show foreign accounts as "2,211 USD" with EGP on hover.

#### 4.2 Overview (Summary)

- **Odd:** "Weekly review" is a link but looks like a section label above the KPI row. "Investing rate 0.0% · 0 money
  added" and "Net gain or loss 0 · Income collected 0" on day 15 read as broken, not as "nothing yet". The
  "22%locked until 2027-01-01" text runs together (no space; it appears on Overview and Investments).
- **Cut:** Net worth and What you own are both shown big, and Over time repeats Net worth. "What it is made of" (donut)
  repeats Investments' Allocation donut. "If you sold today" is a second net worth. Fold it into Net worth as one line
  ("If you sold today: 448,464").
- **Link:** *Plan to invest* opens Investments › Planner, which is empty and blocked ("Set target allocation first",
  target total 0.00%). The button leads to a dead end. It should carry the free cash amount and suggest a split even
  without targets (by current allocation). The home page never shows Safe to spend, the one number a lazy user
  wants. "Where money in went" with one category in October draws a Sankey with one ribbon: below three categories,
  use a sentence.
- **Next:** a "Since last visit" strip (new transactions, prices moved, bills paid) would make opening the app rewarding.

#### 4.3 Overview › Spending (Expense analysis)

- **Odd:** the tab says *Spending* and the page title says *Expense analysis*. In the sample's October one category fills
  a full-width treemap: a treemap needs four or more boxes to say anything.
- **Cut:** "How each one moved", "Now against your usual month" and "Inside its usual range?" make three charts of the
  same comparison. Keep the range bar, which is the clearest, and drop the other two.
- **Good:** treemap tiles, range rows and calendar days already open the filtered register, and so do Budget's rows.
  Use this pattern everywhere (see §6).

#### 4.4 Overview › Health

- **Odd:** Emergency fund 0.6 months (see §3.4.3). "Debt to cash", "Debt to net worth" and "Fixed costs to income" are
  analyst ratios: a lazy user needs one sentence per row ("Your loans are 9% of what you're worth: fine").
- **Cut:** each ratio shows twice, as a top card and again under "Against your limits".
- **Link:** Fixed costs to income also appears on Plan › Recurring (34.2%). Keep it in one place and link to it from the other.

#### 4.5 Needs you and Weekly review

- **Odd:** "Your income went up" is printed twice in a row. Nine near-identical certificate items (see §3.4.1).
- **Cut:** Weekly review and Needs you › Bills and payments list the same items. Weekly review should be Needs you plus a
  *Done for this week* button, not a second page.
- **Wire:** group by action ("4 bills to mark paid · Mark all paid") instead of by item.

#### 4.6 Budget

- **Good:** the planned bar and the "about 1,883 a day for 17 days" line.
- **Odd:** the top card repeats Overview's waffle (Saved and invested, 93.2%) instead of answering Budget's question. The
  row "System Categories · Loan payments" leaks an internal group name.
- **Cut:** "Spending by group" (Personal vs System Categories) adds little for one household: fold it.
- **Link:** a row with a schedule (Housing & Rent 12,000 = Landlord) should show "Landlord due 10-03, late" and a *Mark
  paid* button. Today Budget and Cash planning don't know about each other on screen.
- **Next:** "Change one category without the full grid" is already on the roadmap. Add a quick *Move money* between
  rows, YNAB style; the route exists (`budget_move.html`).

#### 4.7 Cash planning

- **Odd:** four KPI cards show four different cash numbers (181,682 / 208,602 / 1,370 / 180,331). "Bills and loan
  payments before next income 1,370" sits beside a list where 15,090 is already late. The 30-day timeline crowds its
  labels ("Landlord +4", "North Cairo Ele…").
- **Cut:** "Lowest point ahead" (card) repeats the forecast chart's subtitle. Free cash repeats Overview.
- **Link:** Safe to spend, the app's best answer to "can I spend?", exists only here. Put it on Home (§3.1).
- **Next:** what-if ("If I buy a 30,000 phone in instalments, what happens to my lowest point?"). Every input already exists.

#### 4.8 Investments

The companion report covers the structure. On screen:

- **Odd:** the holdings table needs 1,245 px and gets 1,022 at a 1440 px window, so *Total return*, *Since purchase* and
  *Horizon* are hidden off the right edge. *Total return* and *Since purchase* hold the same value in every row. Prices
  show with no currency: QQQM "Average cost 11,108" (EGP per unit) sits beside "Price 247" (USD). On the holding page,
  "Average cost 215" (EGP cost at today's rate) is labelled as what you paid, but in dollars it was 220.63.
- **Cut:** Investments' first card is the savings-rate waffle again. Of the holding page's four KPI cards, two say +13,218
  and two say +14.9%.
- **Odd naming:** the *Financial assets* list shows "18K gold price reference" as an investment, and the certificate's
  "ticker" is `NBE-3-YEAR-CERTIFICATE-1`. Exchange menus read "EGX · XCAI": drop the MIC.
- **Wire:** *New investment* (define the instrument) and *Add holding* (own it) are two forms. A lazy user wants "I bought
  10 COMI": search, units, total, done. The instrument record should be created silently from the catalogue pick.
- **Next:** see the companion report.

#### 4.9 Certificates (deposit page)

- **Odd:** a 7,725 px page; see §3.4.1. Principal shows "100,000.00 EGP" with decimals while the rest of the app uses
  whole pounds.
- **Wire:** "Forecast account: CIB · CIB Payroll" should be the same account the matching looks in, and pre-filtered.

#### 4.10 Accounts

- **Odd:** two blue KPI figures of nearly the same size (596,179 vs 602,179) with no difference shown. "Transactions"
  count is the third column, which few people care about. The list is alphabetical, not grouped the way the sidebar groups.
- **Add account** (owner's example): see §5.1.
- **Account page:** the header shows "Balance 114,211" for a USD account without the currency. The register mixes eight
  "Investment revaluation · System-generated" rows into eleven, so real activity is buried: fold system rows into one
  monthly line, or hide them behind a filter. Amounts show "-3,410.00" with decimals while the sidebar shows whole pounds.
  "Review activity" floats as a bare link above the title.
- **Header buttons:** *Other currencies* and *From SMS* on the Accounts list are not about accounts. Move Currencies to
  Wealth and SMS into Import.
- **Next:** a balance-over-time sparkline and "This month in/out" on each account page.

#### 4.11 Settings

- **Odd:** "Database file /home/…/sample.db" is a developer path shown to users. "Settings in each tab" is a sign the
  settings are scattered.
- **Cut:** the Counterparties page shows "Aliases · 0" on every row: hide zero counts. Categories show three type
  buttons (− Expense, + Income, ± Both) and a Recurring/One-off switch on each of 33 rows: move them into an edit drawer.
- **Next:** one "Clean up" assistant (merge duplicate names, archive unused categories, find uncategorised rows) instead
  of three admin tables.

#### 4.12 Search (Ctrl K)

Good idea, hidden: the placeholder "Search pages, accounts, actions or #tags" is right. Promote it as the "Do anything"
box ("pay rent", "buy COMI", "add CIB") that pre-fills forms. It is the lazy user's best friend.

### 5. The lazy-user test: five everyday jobs

| Job | Today | Target |
|---|---|---|
| Add my CIB account | Type a name, pick an institution, change Type, check Currency, starting balance, Held for, Notes (7 fields) | Tap the CIB tile. Name "CIB · EGP", type Bank and currency are filled. Type the balance. **2 actions** |
| Add my THNDR account with what I hold | Add account (Type change), then Investments › Holding I already own, per holding: account, Choose…, units, cost, date | Tap THNDR: type Brokerage, market EGX. Then "What do you hold?" with a ticker list and units. **1 screen** |
| "I bought 10 COMI for 920" | Account page form: date, search, Buy, units, amount or price, fees mode | Ctrl-K "buy 10 comi 920", or one row: ticker, units, total |
| "How much can I spend till payday?" | Overview shows Free cash; Safe to spend is on Cash planning; Left in plan on Budget | One hero number on Home and the phone's first screen |
| "Did I pay rent?" | Cash planning list or Needs you | Budget's Housing row shows "Landlord · late 12 days · Mark paid" |

#### 5.1 The owner's example, taken further: Add account

Designs 004 built the pick list. The next step makes the institution the *first and only required* choice:

1. **Pick the institution first** (tiles, short code or Arabic search: "cib", "الأهلي", "thndr"). Add the common short codes
   people type ("NBE", "QNB", "AAIB", "HDB") and the app names ("Thndr", "Vodafone Cash").
2. **Infer the rest** from `institutions.csv` `kind`: broker → Brokerage, wallet → Cash wallet, bank → Bank. The currency
   defaults to EGP, with the user's other currencies as chips. The name becomes "CIB · EGP", editable.
3. **Ask one question by kind:** bank → "Current or certificates?"; broker → "Which markets?"; wallet → nothing.
4. **Balance** last, with today's date and "I'll import instead" as a button, not a paragraph.
5. **Hide** Held for and Notes behind *More*.
6. **Extend the list:** only 4 brokers today (THNDR, EFG Hermes, Azimut, CI Capital). Add the other EGX brokers the
   target users have (e.g. Mubasher Trade, Beltone, Naeem, HC, Pharos, Arqaam, Prime) and the foreign ones Egyptians use
   (Interactive Brokers, eToro, Saxo, Swissquote). The companion report needs this for its market defaults.

### 6. Linking map: what should open what

| You see | Clicking it should open |
|---|---|
| Any hero number | Its bridge (the Safe-to-spend bar pattern), then the rows behind each bar |
| A category name anywhere | That category's register, same period (already done on Spending, Budget and the Overview's flows; keep it the rule) |
| A counterparty name | Its history and total this year, with *Make a rule* |
| A bill in Budget, Plan, Needs you | The same bill sheet: due date, last paid, *Mark paid*, *Edit schedule* |
| A holding in Overview's donut or Biggest holdings | The holding page |
| A KPI "0" (nothing yet) | What would make it move ("No investment this month · Plan to invest") |
| Late bill, idle broker cash, unmatched interest | Needs you, grouped by action |

### 7. Small things seen (one line each)

- "22%locked until …" has no space (Overview, Investments): `lightning/ui/templates/dashboard/index.html:72`.
- Holdings table overflows at 1366 and 1440 px (1,245 px needed).
- Account type menu truncates "Bank account (current or…".
- "Cash" and "Cash wallet" are two types with near-identical names, and "Other" and "Physical asset" both land under
  Other Investments.
- Balance placeholder "0.00" teaches decimals the app hides elsewhere.
- Prices page shows "1.0000 pieces", "80.0000 units", "53,100.0000" (four decimals).
- Currencies page rate "1 USD = 51.600000 EGP" (already filed separately).
- Register balance column repeats "EGP" or "USD" on every row.
- Income collected says "Year to date" while the page is set to Monthly.
- Expense analysis day calendar marks days after today with empty pills.
- Over time chart y-axis "1,000,000" for a 546k series wastes half the height.

### 8. Next expansion, in order

**Now (polish what exists, no new features)**
1. One name per figure; retire the duplicates in §3.1 and rename the two "Bills due".
2. Cut subtitles and zero columns (§3.2); add the (i) pattern.
3. One home per page (§3.3).
4. Smart wiring (§3.4): certificate auto-match, follow held markets, spendable switch, people-only owner pickers,
   institution-first account form, late bills first.

**Next (make it feel like one organism)**
5. Home = three heroes + Needs you grouped by action + "since last visit".
6. One bill sheet and one category sheet used by every tab.
7. Ctrl-K as "Do anything" with natural entries.
8. Brokerages with currency pockets and multi-market analysis (companion report).

**Later (expansion)**
9. What-if planner on Cash planning (purchase, raise, job change).
10. Goals as reserves with a date and a picture ("Car by 2027-06").
11. Yearly story (December): where it went, what grew, what the pound did to you.
12. Shared household (two profiles, one view): the custody model already supports it.

### 9. Questions for the owner

1. **Three heroes:** are Net worth, Spendable until payday and Left this month the right three? Or should Safe to spend
   replace Left this month?
2. **Spendable cash:** should brokerage and foreign-currency cash be left out of Free cash and Safe to spend by default?
3. **Emergency fund:** should it count only the reserve (today) or also free cash?
4. **Sitemap:** may Currencies, Certificates and Zakat move under one *Wealth* tab (the current Investments tab, renamed)?
5. **Guideline:** several fixes here (dropping subtitles, hiding zero columns, the (i) pattern) need a rule in A-part. Do
   you want them proposed as a guideline change first?

## Fix

Built 2026-10-16 (Claude with three Sonnet helpers; branch `claude/product-ux-audit-report-qgqmwy`, merged to main).

- **§3.1:** "Budget left to spend" is now "Budget until payday". What you owe's row is "Bills due, loans apart". Savings rate shows its period beside it.
- **§3.4:**
  - Certificate interest: suggested receipts, *Match all*, and one Needs-you item per certificate (item 1). Mohab's Needs you goes from 14 to 6.
  - Held markets are followed automatically (2).
  - Health shows months of cash you own beside the reserve (3).
  - Owner pickers list people only, using `counterparties.kind` (4).
  - Brokerage and foreign cash are **Kept apart** from Free cash and Safe to spend, with a per-account override (5).
  - Picking an institution sets the account type (6).
  - "Planned" replaces "Bill linked" (7).
  - Late bills show "Late · N days" and sort first (9).
  - The locked certificate shows as "not counted until" (10).
- **§3.5:** Add account asks the institution first, with Held for and Notes under More. Loan matching settings are folded away.
- **§4:** "Your income went up" appears once. *Plan to invest* opens a planner that works without targets. Prices show no trailing zeros and carry their currency. A USD account's header reads in USD. MIC codes are gone from the exchange picker. Counterparties hide "Aliases · 0".
- **§5.1:** 11 brokers added, with `markets` and `home_currency`.

**Still open:**
- §3.1: three hero numbers.
- §3.2: cutting subtitles, and the (i) pattern.
- §3.3: one home per page (sitemap).
- §3.4 item 8: a raise prompt on Budget.
- §4: folding revaluation rows on the account page, the holdings table's width at 1440 px, and saved views as one menu.
- §8: Next and Later.

Correction to §4.8: *Total return* and *Since purchase* are not duplicates. They differ after a year or a sale, so both stay.

Round 2, 2026-10-16 (the owner said: pick what is sensible):

- §3.4 item 8: a raise prompt on Budget.
- §3.5: saved views are one *Views* menu.
- §4.10: value updates are folded on account pages.
- §4.8: the holdings table fits 1366 px.
- §3.2: the subtitles named there are gone, and price sources sit behind *Where prices come from*.

**Still open:** three hero numbers (§3.1), one home per page (§3.3), and §8 Next and Later.
