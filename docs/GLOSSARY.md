# Glossary and taxonomy

Canonical product and technical terms. The product story is in [Project Overview](PROJECT_OVERVIEW.md), calculation contracts in [Architecture](ARCHITECTURE.md), and the visual system in the [Brand guideline](../guideline/) (`app.html`, `website.html`, `phone.html`). The figures table under "Reported figures" is generated from `lightning/core/figures.py` (`python -m lightning.core.figures`), and `tests/test_figures.py` keeps the two in step: change a figure there, never here.

## Contents

Look up one term with `grep -n -i '<term>' docs/GLOSSARY.md`. Read a whole section only when you add or rename terms in it.

| Section | Holds |
|---|---|
| The basic model | Ledger, accounts, transactions, postings and the other core nouns |
| Device authority | Home node, borrower, checkout, checkpoint and hand-back receipts |
| Three layers: ledger, plan, report | What each layer may do |
| Reported figures: one name, one calculation, one function | Every figure a screen shows, its formula and its function (generated) |
| Category taxonomy (why the activity happened) | L1, L2 and L3 categories |
| Names and identifiers | Names versus codes |
| Asset and account taxonomy (what vs where) | Asset classes and account kinds |
| Transaction and posting types | Every transaction and posting type |
| العربية — المسرد العربي | المصطلحات والأرقام المالية بالعربية المصرية |

This is Lightning's canonical language for product, database, code, and UI. Use these definitions consistently. The user's visible label is the **Name**; IDs and codes support data integrity and lookup and should not clutter ordinary screens.

## Device authority

The first table describes built v1 lending. The planned replacement follows below; it does not change the current runtime.

| Term | Meaning |
|---|---|
| **Home node** | The device holding the centralized accepted database and deciding which device may write. The phone is the intended default. |
| **Borrower** | A paired device holding temporary write authority for one checkout; initially a PC. |
| **Checkout** | One grant of write authority, identified by a random checkout ID and increasing home epoch. |
| **Checkpoint** | An immutable, verified encrypted database version with an ID and ciphertext hash. The live home file may later change. |
| **Lend** | Home records a grant and becomes read-only before the borrower enables writes. |
| **Hand back** | Borrower freezes its working copy and returns an encrypted candidate for home verification and publication. |
| **Received** | Home durably holds a complete ciphertext candidate; the borrower remains read-only, and home has not resumed writing. |
| **Accepted** | Home has verified and durably published the candidate and issued a durable receipt for its new checkpoint. |


Planned [edit journal](proposals/edit_journal.md), not built:

| Term | Meaning |
|---|---|
| **Home** | The stable device that validates proposed edits and publishes confirmed results; it changes only through an explicit move or recovery. |
| **Proposal** | An immutable, signed request to perform one domain action, with a durable origin identity and preconditions. |
| **Pending edit** | A locally saved proposal awaiting a terminal home decision; visible locally but excluded from confirmed reports. |
| **Confirmed change** | The home's durable accepted result, replicated exactly rather than recalculated by peers. |
| **Decision receipt** | The durable outcome tied to a proposal's identity and content hash, retained in compact form to prevent replay. |
| **Authority generation** | One home-authority history; explicit home replacement advances it. |
| **Confirmed cursor** | Generation, decision revision and commit hash identifying contiguous applied progress. |
| **Origin incarnation** | One device installation's sequence namespace, renewed when safe counter continuity cannot be proved. |
| **Field group** | Fields whose preconditions and updates must be checked together to preserve a domain action's meaning. |
| **Outbox** | The device's encrypted durable queue, preserved independently of its confirmed replica. |

## The basic model

Each term belongs to one layer: **Ledger** (real money that actually moved), **Plan** (what-if; moves no money) or **Report** (read from the other two). See [Three layers](#three-layers-ledger-plan-report).

| Term | Layer | Meaning | Example |
|---|---|---|---|
| **Account** | Ledger | Where value is held. | CIB, Cash wallet, THNDR brokerage |
| **Financial asset** | Ledger | What value is held or counted in an account. Designed as an extensible type so new products can be added without changing the account model. | EGP cash, COMI share, fund unit, CD, gold gram |
| **Asset class** | Ledger | A grouping for financial assets; describes what kind of wealth it is, not where held or why a payment happened. | Funds → Money Market |
| **Exposure** | Ledger | What economic value an asset tracks, separately from its wrapper/class. | Gold fund → Gold exposure |
| **Holding / position** | Ledger | Calculated quantity of one financial asset in one account at a date. | 100 COMI shares in THNDR |
| **Physical item** | Ledger | Individually named tangible asset tracked by piece count, per-piece net gold-bearing weight, karat, cost, and valuation reference. Its item record is not a tickered security. | One Gold ring, 1 piece, 4.2 g of 18K alloy |
| **Net gold weight** | Ledger | Grams of gold-bearing alloy per physical piece, excluding stones and non-gold parts. It is not fine-gold grams unless the item's karat is 24K. | Ring: 4.2 g at 18K |
| **Fine-gold exposure** | Ledger | Pure-gold-equivalent grams derived for allocation/reporting: piece count × net gold grams per piece × karat/24. This reporting measure does not change the item's display weight or reference valuation formula. | 1 × 4.2 g × 18/24 = 3.15 g fine gold |
| **Karat-specific gold price** | Ledger | Price per gram of alloy at the named karat. Multiply by matching-karat net gold weight; never adjust the quote by purity again. | EGP per gram of 18K gold |
| **Acquisition cost** | Ledger | Historical total paid for the item's current acquired quantity; may include workmanship, stones, and fees. Reference-price updates never change it. | 18,000 EGP including workmanship |
| **Manual item valuation** | Ledger | User-entered dated total value for a physical item and its held quantity, used when the shared gold price is unsuitable. | Ring's 2026-09-26 resale estimate |
| **Balance** | Ledger | Calculated value/quantity of an account or position on a date; not an independent user-entered fact. | 12,000 EGP; 100 shares |
| **Activity** | Ledger | The broad reason/kind of a transaction, represented by its category family. It is independent of whether money came in or went out. | Personal, Work, Investment |
| **Category** | Ledger | A label for the activity behind a transaction. Categories do not describe the counterparty, account, or owned asset. | Personal → Food & Groceries |
| **Counterparty** | Ledger | The canonical person, business, institution, or own account on the other side of a transaction. A saved canonical name can have confirmed aliases; close matches are suggestions and require an explicit user decision. | Talabat, employer, CIB |
| **Confirmed alias** | Ledger | User-approved alternative spelling attached to one canonical Counterparty; up to ten per Counterparty. A typo suggestion is not an alias until confirmed. | “Talbat” saved for Talabat |
| **Search suggestion** | Ledger | A ranked possible match shown to help recover from spelling mistakes; it never silently chooses an identity, transfer, category, or custody owner. | “Did you mean Talabat?” |
| **Transaction** | Ledger | A dated user or system event shown in the main ledger. | 450 EGP Talabat payment |
| **Main ledger** | Ledger | The single activity ledger from which account registers, all-transaction view, budget actuals, and reporting are derived. | Register filtered to CIB |
| **Ledger line / journal line** | Ledger | One transaction's effect on a particular account and financial asset. | CIB cash −450 EGP |
| **Profile currency** | Ledger + Report | The currency used for ledger amount and report totals; fixed once monetary history exists. | EGP |
| **Amount in currency** | Ledger | The amount in the line's own currency, preserved with its dated profile-currency value and rate. | 100 USD recorded as 5,000 EGP at 50 EGP/USD |
| **FX revaluation** | Ledger + Report | Month-end change in the profile-currency value of foreign cash already held; it changes no native units and is not income or spending. | 100 USD rises from 5,000 to 5,500 EGP |
| **Owner ID** | Ledger | Optional Counterparty reference on a ledger line (shown as **Held for**); blank means the user owns the value on that line. | Dad owns 2,000 EGP of THNDR cash |
| **Money in / money out** | Ledger | Direction in which value crosses an account boundary. Direction does not determine category. | Salary is money in; grocery purchase is money out |
| **Transfer** | Ledger | Value moved between accounts owned by the user; not income or expense. Selecting an owned account as Counterparty creates both account effects. | CIB → THNDR |
| **Investment trade** | Ledger | Exchange of brokerage cash for asset units (buy) or units for cash (sell). It is recorded inside that brokerage account's register. | Buy 10 fund units |
| **Budget** | Plan | Planned spending amount attached to a category/group and month. Budget limits are not reserve accounts or ledger transactions. | Monthly Food limit |
| **Financial health** | Report | A read-only profile of named financial figures, their periods, supporting amounts and personal limit comparisons. It does not create a score or change financial data. | Financial health page |
| **Financial health limit** | Report | A profile-owned comparison preference for a named figure. Minimum limits pass on equality or above; maximum limits pass on equality or below. An unavailable figure receives no judgement. | Savings rate at least 20% |
| **Monthly base budget** | Plan | A tracked category’s monthly plan before any carryover: fixed EGP, a selected percentage of Average monthly income, or an observed-month spending average. Shown as **Base budget**. | Food fixed at 3,000 EGP or 10% of income |
| **Observed-month average** | Plan | Spending average whose 3m/6m window is divided by the distinct months with qualifying recorded activity. Months without activity are not treated as zero and the window is not extended backward. | 12,000 EGP across two observed months in a six-month window = 6,000 EGP |
| **Budget carryover** | Plan | Optional unused spending room added to a later month's limit. It never sets aside cash, creates a transaction, or reduces free cash. | 500 EGP of unused Food limit carried into October |
| **Held for** | Ledger | Who the money or units in the user's account actually belong to, when not the user. Separate from Counterparty: one identifies transaction context, the other identifies beneficial owner/custody. The field is called Held for on every form (formerly Whom / Owned by / Owner). | Dad owns part of THNDR cash |
| **Change ownership** | Ledger | A zero-sum cash entry that reassigns part of one account's balance between the user and one saved person. It changes beneficial ownership, not the account's gross balance. | Set aside 5,000 EGP in CIB for Dad |
| **Expense paid for you** | Ledger | An expense the user chooses to record in their account even though another person paid externally. The categorized, user-owned expense is paired with an equal custody amount for the payer, so gross account cash stays unchanged. | Dad paid 2,500 EGP for groceries; record the expense and mark that cash as Dad's |
| **Reserve** | Plan | A plan assigning some already-owned cash to an emergency fund or future goal. Assignment does not itself move money or change net worth; the actual payment is a normal ledger transaction. | Rent reserve |
| **Emergency fund** | Plan | Permanent, dedicated reserve section. Coverage = Reserves for emergencies ÷ Average monthly income (or ÷ Average monthly spending, if Settings › Budget says so), shown in months. The aim is six. | 13 months of average monthly income |
| **Cash planning** | Plan | The tab for spendable cash and commitments. Sub-tabs: Plan, Recurring, Loans, Reserves. Nothing in it posts to the ledger on its own. | — |
| **Recurring item** | Plan | A bill, subscription or income that repeats on a schedule (weekly, monthly, every 3 months, yearly, or once). | WE Internet · 650 EGP monthly on day 20 |
| **Loan** | Plan | A loan or installment plan, entered as its payments: amount per payment, the next payment date, and payments left. Optional amount borrowed. Each payment counts as spending when paid, in System Categories › Loan payments unless another category is chosen. While that category has no budget rule, its Planned amount each month is the loan payments scheduled that month (shown as *Loan payments scheduled this month*); setting an amount replaces it; paying one lowers cash, spending room and loans still to pay together, so it does not change net worth. | Car loan · 24 × 2,500 EGP from 2026-10-05 |
| **Payment status** | Plan | For each scheduled date: **Paid** (settled by a posted transaction), **Skipped** (the user says it won't happen), **Due** (the date is today or earlier and nothing settled it) or **Upcoming**. Voiding the linked transaction makes it Due again. | Rent · 2026-10-03 · Upcoming |
| **Cash forecast** | Plan | An estimate that carries free cash forward month by month with scheduled payments, separately labelled projected CD proceeds, Left in plan after bills, Saving for goals, Emergency fund top-up and Rest of savings target. A bill in a budgeted category counts inside that budget, never on top. Projected CD principal is a transfer into spendable cash, not income; the forecast never changes net worth or free cash. | 2026-11 ends with 93,220 EGP |
| **CD terms** | Plan | The dates and interest rules for a funded certificate account: start, earliest withdrawal, maturity, principal, annual rate, simple-interest payout or compound capitalization frequency, and destination. Terms forecast cash but never post it. | NBE CD · 18% simple · monthly payout |
| **Earliest withdrawal date** | Plan | First date a CD can be redeemed early; it is not a promised payout. Before this date the CD is not immediately realizable. Maturity is when the normal principal return is projected. | Earliest withdrawal 1 March; maturity 1 September |
| **Sale factor** | Plan | User-selected 0–100% estimate of what one asset class would fetch if sold today; 95% when not set. The same factors feed Holdings after sale on Investments and If you sold today on Overview. A CD with terms uses its class factor as an early-redemption estimate only after its earliest withdrawal date; at maturity its remaining principal uses 100%. It does not change holdings or what you own. Historical scenarios use current settings. Formerly *liquidation factor*. | Gold 90%; CD early redemption 95% |
| **Revaluation** | Ledger | Change in investment value caused by price changes, not deposits, purchases, or withdrawals. | Shares appreciate by 1,000 EGP |
| **Opening adjustment** | Ledger | A holding entered as already owned when tracking began; it establishes a baseline and is not period contribution. | 5,000 EGP cost basis entered on tracking start |
| **Reevaluation ledger** | Ledger | Monthly per-account/per-asset record of units, prices, values, and returns. Its account-level total links to one generated journal transaction in the main ledger. | September COMI return detail linked to one THNDR `VAL` journal |
| **System-generated posting** | Ledger | An auditable ledger transaction created by application rules, not manually entered by the user. | Monthly `VAL` journal |
| **Cost basis / average cost** | Ledger | Remaining units' recorded acquisition cost, including buy fees when fees are included in total. | Remaining shares cost 9,500 EGP |
| **Realized / unrealized return** | Report | Gain/loss from units sold / change in value of units still held. | Sale gain / current paper gain |
| **XIRR** | Report | Annualized money-weighted investment return from dated cash flows and an ending value. A since-inception rate and a selected-period currency return answer different questions; an unavailable result needs an explanation. | Portfolio XIRR since first contribution |
| **Opening balance** | Ledger | A separately dated ledger entry for the account's value at a chosen point. It does not set a minimum date for later-entered activity; users can add earlier transactions at any time. | CIB starts at 50,000 EGP on 1 January; a December transaction may be added later |
| **Void / delete** | Ledger | A recoverable correction that removes a transaction from active balances while retaining history. | Void a duplicate import |
| **Linked (import row)** | Ledger | A statement row tied to a transaction you already recorded, instead of posting it again. It moves no money and changes nothing on the transaction; one row per account per transaction. | The CIB statement's Carrefour −450.00 linked to the purchase entered on the phone |

<!-- figures:start (generated by python -m lightning.core.figures) -->
## Three layers: ledger, plan, report

Lightning keeps real money and plans apart, and reports on both:

| Layer | What it holds | Where in the code | Moves money? |
|---|---|---|---|
| **Ledger** (real money) | Real money: posted transactions and the balances and prices they give. | `lightning.accounts`, `lightning.transactions`, `lightning.assets`, investment trades in `lightning.investments` | Yes. Every posted transaction. |
| **Plan** (what-if) | What-if: budgets, reserves, scheduled bills and loans, sale factors and forecasts. Moves no money. | `lightning.budgeting`, `lightning.reserves`, `lightning.planning` (items, payments, forecast), sale factors | No. Recording a payment from the plan posts an ordinary ledger transaction. |
| **Report** | Reads the ledger and the plan and presents them; stores nothing. | `lightning.reporting`, `lightning.planning.position`, `lightning.investments.report`, `lightning.integrity`, every screen in `lightning.ui` | No. It only reads the other two. |

The plan reads the ledger; the report reads both. A plan figure never changes a ledger balance, and a report figure is always a formula of ledger and plan figures.

## Reported figures: one name, one calculation, one function

Every figure a screen shows is listed here once. **From** says which layer its inputs come from. A figure with a calculation is a formula of other figures in these tables and is never computed a second way; **Function** is the one piece of code that computes it. Screens show the calculation under the figure.

### From the ledger — real money

| Figure | Meaning | How it is calculated | Function |
|---|---|---|---|
| **In your accounts** | Everything in your accounts, including what you hold for other people. | What you own + Held for others | `planning.position.Position.in_your_accounts` |
| **Held for others** | Money and units in your accounts that belong to other people. | Read directly from the ledger | `reporting.service.ReportingService.money_from_others_total` |
| **What you own** | The value of everything in your accounts that is yours. | Cash you own + Holdings value + Other you own | `reporting.service.ReportingService.net_worth` |
| **Bank and wallet cash** | Your cash in bank accounts and wallets. | Read directly from the ledger | `planning.position.Position.bank_and_wallet_cash` |
| **Brokerage cash** | Your uninvested cash inside brokerage accounts. | Read directly from the ledger | `reporting.service.ReportingService.owned_brokerage_cash` |
| **Cash you own** | Your cash in banks, wallets and brokerage accounts. | Bank and wallet cash + Brokerage cash | `planning.position.Position.cash_you_own` |
| **Deposits** | Your certificates and time deposits, at their balance. They are part of Holdings value. | Read directly from the ledger | `planning.position.Position.deposits` |
| **Holdings value** | Everything you own that is not cash, at its latest value: certificates and deposits, stocks, funds, gold and other assets. Assets that are not cash sit under one roof (owner decision 2026-10-04). | Read directly from the ledger | `planning.position.Position.holdings_value` |
| **Other you own** | Anything you own that is neither cash nor a holding. | What you own − Cash you own − Holdings value | `planning.position.Position.other_you_own` |
| **Portfolio value** | Holdings value under the name the Investments tab uses: everything you own that is not cash. Cash waiting in a brokerage account counts in Cash you own (owner decisions 2026-10-04). | Holdings value | `planning.position.Position.portfolio_value` |
| **Money in** | Your posted income in the period. Transfers, trades and money held for others are left out. | Read directly from the ledger | `reporting.service.CashFlow.inflows` |
| **Money out** | Your posted spending in the period, after refunds. Transfers, trades and money held for others are left out. | Read directly from the ledger | `reporting.service.CashFlow.outflows` |
| **Net flow** | What was left of money in after money out. | Money in − Money out | `reporting.service.CashFlow.net` |
| **Savings rate** | The share of money in that you kept. When money out is more than twice money in (below −100%, such as a month whose pay came early), the Overview and Financial health say the gap in words instead. | Net flow ÷ Money in | `reporting.service.CashFlow.savings_rate` |
| **Opening balances in the period** | Money and assets you recorded as already yours (opening balances and existing holdings) during the period. They were yours before, so they are not a change. | Read directly from the ledger | `reporting.service.ReportingService.opening_balances_between` |
| **Change in what you own** | How much what you own grew or shrank in the period. | What you own at the end − What you own the day before the start − Opening balances in the period | `planning.position.PositionService.change_in_what_you_own` |
| **Per month** | A period's money out divided by the calendar months it covers, so a year to date compares with a single month. | Read directly from the ledger | `reporting.spending.spending_profile` |
| **Usual month** | The average money out of the last six whole months before the period. | Read directly from the ledger | `reporting.spending._against_history` |
| **Usual range** | The lowest, middle and highest monthly money out of the twelve whole months before the period. It needs three of them. | Read directly from the ledger | `reporting.spending._against_history` |
| **Investing rate** | The share of money in that you moved into investments, out of what you saved, so it is never more than the savings rate. | Money added ÷ Money in | `investments.report.investing_rate` |
| **Average monthly income** | Income in your chosen income categories, averaged over the last 3 or 6 completed months (Settings › Budget). A month with no pay counts as 0 once pay has started; months before the first pay are skipped. Until a completed month has income, the income set up in Recurring stands in. The budget, reserves and the cash forecast all use it. | Read directly from the ledger | `budgeting.service.BudgetService.income_average` |
| **Average monthly spending** | Money out in your budget categories, leaving out investments and one-off categories, averaged over the same 3 or 6 completed months as Average monthly income. The emergency fund can be counted in it (Settings › Budget). | Read directly from the ledger | `budgeting.service.BudgetService.spending_average` |
| **Spent** | Money out in the category this month. | Read directly from the ledger | `budgeting.domain.BudgetLine.actual` |
| **Cost** | What you paid for the units you still hold. | Read directly from the ledger | `investments.report.build_investment_report` |
| **Unrealized gain** | Gain or loss on units you still hold. | Holdings value − Cost | `investments.report.build_investment_report` |
| **Price change on what you hold** | How unrealized gain moved in the period. | Unrealized gain at the end − Unrealized gain at the start | `investments.report.investment_period` |
| **Gain from sales** | Sale proceeds less the cost of the units sold. | Read directly from the ledger | `investments.report.build_investment_report` |
| **Dividends and interest** | Distributions and interest received. | Read directly from the ledger | `investments.report.build_investment_report` |
| **Net gain or loss** | What your investments earned or lost in the period: sales, price changes and payouts. | Gain from sales + Price change on what you hold + Dividends and interest | `investments.report.investment_period` |
| **Money added** | Cash moved into investment accounts from outside, less cash taken out. | Read directly from the ledger | `investments.report.build_investment_report` |
| **Typical move** | How much a holding's month-end price usually moves in a month: the spread (standard deviation) of its monthly price changes, once there are three. | Read directly from the ledger | `investments.journey.holding_history` |
| **Fall from its high** | How far a holding's month-end price sits below the highest month-end price before it, in percent. | Read directly from the ledger | `investments.journey.holding_history` |
| **Average cost** | What you paid for each unit you still hold, fees included. | Cost ÷ Units | `investments.domain.Position.average_cost` |
| **Growth** | Net gain or loss as a share of what the portfolio started the period with, plus money added. | Net gain or loss ÷ (Portfolio value at the start + Money added) | `investments.report.period_growth` |

### From the plan — what-if

| Figure | Meaning | How it is calculated | Function |
|---|---|---|---|
| **Reserves** | Cash you set aside for emergencies and dated goals, less what linked payments already used. It stays in your accounts and in what you own. | Read directly from the plan | `reserves.CashReserveService.breakdown_at` |
| **Bills due** | Bills, subscriptions and loan payments dated today or earlier that nothing has paid yet. | Read directly from the plan | `planning.domain.WhatYouOwe.bills_due` |
| **Loans still to pay** | Every loan payment not paid yet, due or upcoming. | Read directly from the plan | `planning.domain.WhatYouOwe.loans_still_to_pay` |
| **What you owe** | Payments you are certain to make: bills already due and loans. | Bills due (other than loan payments) + Loans still to pay | `planning.domain.WhatYouOwe.total` |
| **Bills and subscriptions a month** | What your recurring bills and subscriptions come to in a month: a weekly one counts 52 times a year, a yearly one once, a one-off payment not at all. | Read directly from the plan | `planning.health.HealthService.bills_a_month` |
| **Loan payments a month** | What your loan payments come to in a month, counting only loans with payments still to make. | Read directly from the plan | `planning.health.HealthService.loans_a_month` |
| **Base budget** | The amount the budget rule gives: fixed, a share of income or an average. | Read directly from the plan | `budgeting.domain.BudgetLine.budget` |
| **Plan leaves to save** | What this month's plan leaves of average monthly income. | Average monthly income − Planned | `planning.health.PlanCheck.plan_saves` |
| **Planned savings rate** | The share of average monthly income this month's plan leaves unspent. Financial health compares it with your Savings rate limit; the budget and Needs you warn when it falls short. | Plan leaves to save ÷ Average monthly income | `planning.health.PlanCheck.planned_savings_rate` |
| **Savings target** | What your Savings rate limit (Financial health) asks you to keep each month: Average monthly income times that limit. | Read directly from the plan | `planning.health.PlanCheck.savings_target` |
| **Emergency fund top-up** | What the emergency fund lacks to reach six months, spread over two years (owner request 2026-10-05). Nothing once the fund is full. | Read directly from the plan | `budgeting.domain.EmergencyFund.top_up` |
| **Saving needed** | What this month's plan must leave: the Savings target, or Saving for goals plus Emergency fund top-up when they need more. | Read directly from the plan | `planning.health.PlanCheck.to_save` |
| **Most you can plan** | The largest plan that still leaves what you need to save. It replaced the budget's separate spending ceiling (2026-10-05). | Average monthly income − Saving needed | `planning.health.PlanCheck.spending_room` |
| **Bills inside the plan** | This month's scheduled bills, due or upcoming, in a category that has a budget. They are part of that budget. | Read directly from the plan | `planning.forecast.CashForecaster.forecast` |
| **Bills and loan payments before next income** | Scheduled bills, subscriptions and loan payments that are not due yet, up to your next income. | Read directly from the plan | `planning.forecast.CashForecaster._safe_to_spend` |
| **Saving for goals** | What dated reserve goals still need this month, spread over the months left. | Read directly from the plan | `planning.forecast.CashForecaster._goal_need` |
| **Rest of savings target** | What the Savings target asks a month beyond Saving for goals and Emergency fund top-up (never below zero), so Safe to spend never counts what you mean to save (owner decision 2026-10-05). | Savings target − Saving for goals − Emergency fund top-up | `planning.forecast.CashForecaster.forecast` |

### Ledger + Plan — real money after your plans

| Figure | Meaning | How it is calculated | Function |
|---|---|---|---|
| **Net worth** | What you own after what you owe. | What you own − What you owe | `planning.position.Position.net_worth` |
| **Debt to net worth** | What you owe for each pound of net worth. None when net worth is zero or less. | What you owe ÷ Net worth | `planning.health.Ratio.percent` |
| **Debt to cash** | What you owe for each pound of cash you own: could your cash clear it today? | What you owe ÷ Cash you own | `planning.health.Ratio.percent` |
| **Loan payments to income** | The share of your income that goes to loan payments, counting only loans with payments still to make. | Loan payments a month ÷ Average monthly income | `planning.health.Ratio.percent` |
| **Fixed costs to income** | The share of your income already promised to bills, subscriptions and loan payments. | (Bills and subscriptions a month + Loan payments a month) ÷ Average monthly income | `planning.health.Ratio.percent` |
| **Free cash** | Cash you can spend without touching reserves or leaving a bill unpaid. | Cash you own − Reserves − Bills due | `planning.position.Position.free_cash` |
| **Holdings after sale (estimate)** | What your holdings, deposits included, might fetch if sold or cashed in today, after each class's sale factor. CDs before their earliest withdrawal count 0; early-redeemable CDs count their balance × the CD sale factor; matured CDs count their balance. | Σ Holdings value of each class × its sale factor | `planning.position.Position.holdings_after_sale` |
| **If you sold today (estimate)** | Free cash plus what your holdings might fetch. | Free cash + Holdings after sale (estimate) | `planning.position.Position.if_you_sold_today` |
| **Change in net worth** | How much net worth grew or shrank in the period. | Net worth at the end − Net worth the day before the start − Opening balances in the period | `planning.position.PositionService.change_in_net_worth` |
| **Carryover** | Unused plan from last month, added to this month when carryover is on. | Left in plan last month | `budgeting.domain.BudgetLine.opening_carryover` |
| **Planned** | What you plan to spend this month. The month's total also counts background estimates for untracked categories; one from a single month of spending is low confidence and shows a "!" that says why. | Base budget + Carryover | `budgeting.domain.BudgetLine.available` |
| **Left in plan** | What is left of the plan; the Overview and Budget show the same month figure, and a negative one reads "Over plan". One-off categories are left out of Spent. | Planned − Spent | `budgeting.domain.BudgetLine.remaining` |
| **Safe to spend** | Free cash after what is promised before your next income. An estimate. Budget left to spend, Saving for goals, Emergency fund top-up and Rest of savings target count for every month until that income (only the days before it in the month it lands), so a long gap between pays is covered. | Free cash − Bills and loan payments before next income − Budget left to spend − Saving for goals − Emergency fund top-up − Rest of savings target | `planning.forecast.CashForecaster._safe_to_spend` |
| **Budget left to spend** | This month's left in plan less the scheduled bills it already covers, so a bill is never counted twice. | Left in plan − Bills inside the plan | `planning.domain.ForecastMonth.budget_spending` |

### Entry-form fields

Forms that record values use the same field names everywhere.

| Field | Layer | Meaning | Replaces |
|---|---|---|---|
| **Date** | Ledger | The day money moved. | Date paid, Date received |
| **As of** | Ledger | The day a balance, holding, price or value is true. | Price date, Statement date |
| **Amount** | Ledger + Plan | Money moved, in the account's currency. A trade's amount includes fees unless *Fees are extra* is ticked; a scheduled item's amount is each payment. | Total paid, Total paid / received, Each payment, Total amount received |
| **Balance** | Ledger | An account balance on the As of date. | Statement closing balance |
| **Value** | Ledger | What a holding or item is worth on the As of date. | Total item value, Current value |
| **Cost** | Ledger | What you paid in total for units you already hold, fees included. | What you paid in total, Invested capital |
| **Units** | Ledger | Shares, fund units, grams or pieces. | Quantity, Pieces, Units you hold |
| **Account** | Ledger + Plan | Where the money moves or the holding sits. | Held in, Received into, Paid from, Paid into |
| **Cash account** | Ledger | The account that pays or receives the cash for a trade in another account. | Paid from / received into, Money goes to |
| **Counterparty** | Ledger + Plan | Who you paid or who paid you. | Paid to, From, Search counterparty |
| **Held for** | Ledger | The person the money or units belong to, if not you. | Whom, Owned by, Owner, Money held for someone else |
| **Category** | Ledger + Plan | What the money was for. | Search category |
| **Type** | Ledger + Plan | The kind of record. | Kind, Action |
| **Name** | Ledger + Plan | The record's name. | Item name |
| **Notes** | Ledger + Plan | Free text. | Details |
| **Fees** | Ledger | Fees inside the amount (tick *Fees are extra* when they are not). | Fees included in total, Fees are excluded from the total |
| **Due date** | Plan | When a scheduled payment is due; when adding, the next one; when editing, the first. | Next date, Next payment date |
| **Last due date** | Plan | The last scheduled payment, when a recurring item ends. | Last date |
| **Payments left / Number of payments** | Plan | How many loan payments; counted from the first due date. | — |
| **Amount set aside** | Plan | Cash assigned to a reserve. It stays in your account. | Cash reserved, Cash assigned |
| **Target amount** | Plan | What a reserve is saving towards. | — |
| **Sale factor** | Plan | The share of a class's value you expect if you sold today (95% when not set). | Liquidation factor |

### Retired names

These names no longer appear on screens. Each is now called:

| Old name | Now |
|---|---|
| All accounts | In your accounts |
| Gross balances | In your accounts |
| Money from others | Held for others |
| Cash held for others | Held for others |
| Owned value | What you own |
| Owned net worth | What you own |
| What I own | What you own |
| Liquid cash | Cash you own |
| Owned liquid cash | Cash you own |
| Investment cash | Brokerage cash |
| Investments and deposits | Deposits |
| Investment holdings | Holdings value |
| Current owned value | Holdings value |
| Other owned assets | Other you own |
| Assigned reserves | Reserves |
| Assigned to reserves | Reserves |
| Cash reserved | Reserves |
| Estimated liquid investments | Holdings after sale (estimate) |
| Estimated cash after sale | Holdings after sale (estimate) |
| Estimated available value | If you sold today (estimate) |
| Yours | What you own |
| Total spending | Money out |
| Net income less spending | Net flow |
| Cashflow | Net flow |
| Average monthly salary | Average monthly income |
| Budgeted | Planned |
| Current budget | Planned |
| Invested capital | Cost |
| What you paid in total | Cost |
| Unrealized gain/loss | Unrealized gain |
| Change in unrealized value | Price change on what you hold |
| Realized gain or loss | Gain from sales |
| Distributions | Dividends and interest |
| Investment result | Net gain or loss |
| Period result | Net gain or loss |
| Period gain/loss | Net gain or loss |
| Result | Net gain or loss |
| Realized gain | Gain from sales |
| Change in unrealized gain | Price change on what you hold |
| New money in | Money added |
| Left in plan after bills | Budget left to spend |
| Deposits and holdings after sale (estimate) | Holdings after sale (estimate) |
| Investments if sold (estimate) | Holdings after sale (estimate) |
| New money added this period | Money added |
| Cash added and withdrawn | Money added |
<!-- figures:end -->

## Category taxonomy (why the activity happened)

There are three levels in the model, but only two are used now:

- **L1 — Activity family:** Personal · Work · Investment.
- **L2 — Broad category:** the simple, useful analysis bucket within one family.
- **L3 — Detail:** intentionally unused/empty for now. Do not prepopulate it; add only when a user chooses to track more detail.

Examples: `Personal → Food & Groceries`, `Work → Salary`, `Investment → Dividends`. Categories are not divided into income and expense trees: choose the activity that explains the event regardless of sign. For example, a refund should retain the original activity category. Counterparty defaults may suggest a category (Talabat → Personal / Food & Groceries), but the user can choose another.

Categories are selected from an explicit list, not silently created by typing. Names are sorted alphabetically within their parent. A category with historical use cannot be physically deleted; it is archived. Archived categories remain legible on old transactions but cannot be selected for new ones. Names should be unique among siblings; the same broad term may exist under different L1 families when meaning differs (e.g., Transportation under Personal and Work).

## Names and identifiers

| Term | Rule | Example |
|---|---|---|
| **Name** | Human-readable label shown in ordinary app screens. Account codes never appear under account names in normal UI. Canonical Counterparty names are unique; other taxonomy names may repeat under different parents. | CIB; Talabat; Food & Groceries |
| **Code** | Stable machine-friendly identifier for relationships, imports, and technical search. It is not the display name and should not appear in ordinary account UI. | `STK:COMI` |
| **ID** | Internal database key; not meaningful to a person and never displayed. | `account_id = 12` |
| **Ticker / symbol** | Public exchange/provider symbol used to find an instrument. It is not Lightning's code or database ID. | `COMI` |
| **ISIN** | Optional global security identifier, useful for source matching; ordinary users need not know or enter it. | Egyptian security ISIN |
| **Exchange** | Where a stock or ETF trades, stored as its ISO 10383 MIC and shown by its common name. A stock without one is on EGX; funds and gold have none. | `XCAI` shown as EGX; `XNAS` as Nasdaq |
| **Price file** | The closing prices of one market (Egyptian stocks, Egyptian funds, exchange rates, US, Gulf or European stocks), published as one checked folder and refreshed after that market closes. Settings › Price files chooses which ones a profile follows. Code and the collector call it a pack (`lightning/market/packs.py`). | Egyptian stocks, prices to 2026-12-31 |
| **Update prices** | Lightning asks the sources itself for each held investment's latest close and every month-end close it lacks (source `ONLINE`). It does it by itself only on the first open after a month ends, in the background. The shared price files are the backup, offered after two failed tries; Settings › Price files › Test price sources names a failing source. | Fetched 6 prices for 3 investments |
| **Market key** | The price file's name for an instrument, which never changes once published: the venue's ISO 3166 country and the ticker, `EG:FUND:<id>` for a fund, a currency pair for a rate. Stored on the financial asset it matched. | `EG:COMI`, `SA:2222`, `USD/EGP` |
| **Unit** | What is counted for an asset. | EGP, share, fund unit, gram |
| **Transaction reference (ref)** | Fixed human-readable ID assigned to a transaction. It does not change if its date is edited and has no account prefix because transfers can touch two accounts. | `OUT-2026-09-25-003` |
| **Ledger-line reference** | A transaction ref plus its line number. | `TRF-2026-09-26-001/2` |
| **Date input** | Accepts ISO (`2026-01-31`), day/month/year (`31/1/2026`), or day/month (`31/1`, current year); stored canonically as ISO. Ambiguous numeric dates are interpreted day-first. | `31/1` → `2026-01-31` in 2026 |
| **Amount input** | Accepts a number (`1,250.50`, Arabic-Indic digits) or a sum with + - * / ^ and round brackets. Order: brackets, then ^, then * and /, then + and -, left to right; a bracket after a number or a bracket multiplies. Anything unclear is refused with the reason (`-2^2`, `2^3^2`, `8/2(2+2)`, a sign too many or too few, an uneven division, %, a date). The window shows the result before saving. | `3+5*8` → 43; `2(3+5)` → 16 |
| **Tag** | A #word in a transaction's notes: letters, digits, - or _, with at least one letter; case does not matter. A note shows it as a link to every transaction carrying it, headed with their count, Money in and Money out. Typing it in a register's search is the same exact filter. | `#Eid` and `#eid` are one tag; `#eid2026` is another; `invoice #4521` has none |
| **Rule** | Settings › Rules: when a transaction's counterparty (is, contains, one of), notes, amount (is, about ±7.5%, between, more or less than), account or direction fit, all or any of them, it sets a category, adds tags or splits money out (fixed amounts, then percents, the rest to the category). The most specific rule decides. It files imports and register rows before the counterparty's usual category; the past changes only when you ask, with one undo. | Vodafone between 1,000 and 50,000 → Shopping; Vodafone 350 keeps Utilities & Bills |
| **Privacy mode** | Every money amount on screen is blurred, for a café or an office; percentages, dates and names stay readable, and pointing at an amount shows it. Switched by the eye beside Search or by "Hide amounts" in the command bar; the profile remembers it. | 52,500 owed shows blurred; 26.5 % stays |

## Asset and account taxonomy (what vs where)

Financial assets can include currency/cash, stocks, funds, physical gold, deposits/CDs, and future supported asset kinds. Asset class and exposure are separate dimensions: a gold fund is a Fund by wrapper/class but has Gold exposure. Account types describe location/container, for example cash wallet, bank account, deposit account, brokerage, physical-asset location, and other asset account. A brokerage may contain both its cash balance and many investment holdings.

Example internal-code patterns (for data/search, not routine UI labels):

- Account: `INSTITUTION-TYPE-CURRENCY`, e.g. `THNDR-BRK-EGP`.
- Financial asset: `CLASS:SYMBOL`, e.g. `CASH:EGP`, `STK:COMI`, `FND:AZG`, `GLD:21K`.
- Category/asset-class path: dotted tree code; nesting in the UI is by parent, not repeated breadcrumb text on every child.

## Transaction and posting types

`OPN` opening · `IN` inflow · `OUT` outflow · `TRF` internal-account transfer · `BUY` investment buy · `SEL` sell · `DIV` dividend · `VAL` system-generated valuation · `ADJ` reconciliation adjustment · `CNV` conversion (future/multi-currency use).

An investment overview is a filtered/calculated view, not a separate place for buy/sell/dividend entry: those transactions are entered within the brokerage account register. Monthly return details live in the reevaluation ledger; one aggregate per affected account is journaled in the main ledger for reconciliation.


## العربية — المسرد العربي

هذا القسم مرجع عربي للأسماء الأساسية في Lightning. تبقى التسمية الإنجليزية بجوار المقابل العربي لتسهيل مطابقة المصطلحات مع الشاشات والشفرة. التعريف الإنجليزي في القسم السابق هو المرجع التفصيلي عند وجود اختلاف في الصياغة.

### الطبقات الأساسية

| English | العربية | المقصود |
|---|---|---|
| Ledger | السجل | الأموال والحركات الفعلية المسجلة. |
| Plan | الخطة | ميزانيات واحتياطيات ومدفوعات متوقعة؛ لا تنقل أموالاً. |
| Report | التقرير | قراءة للسجل والخطة لعرض النتائج. |
| Account | الحساب | المكان الذي تُحفظ فيه القيمة. |
| Financial asset | أصل مالي | ما يحتفظ الحساب بقيمته أو يسجل كميته. |
| Asset class | فئة الأصل | نوع الثروة، مستقلاً عن مكان حفظها. |
| Exposure | التعرّض | القيمة الاقتصادية التي يتبعها الأصل. |
| Holding / position | حيازة / مركز | كمية أصل مالي في حساب بتاريخ محدد. |
| Balance | الرصيد | قيمة أو كمية الحساب المحسوبة في تاريخ محدد. |
| Transaction | معاملة | حدث مالي مؤرخ للمستخدم أو النظام. |
| Main ledger | السجل الرئيسي | مصدر موحد للحركات وأرصدة الحسابات والتقارير. |
| Ledger line | قيد | أثر معاملة واحدة على حساب وأصل مالي. |
| Money in / money out | أموال داخلة / أموال خارجة | اتجاه عبور القيمة؛ لا يحدد فئة النشاط. |
| Transfer | تحويل | نقل قيمة بين حسابات المستخدم، وليس دخلاً أو مصروفاً. |
| Investment trade | صفقة استثمار | مبادلة نقد الوساطة بوحدات أصل أو العكس. |
| Budget | ميزانيتك | إنفاق مخطط لفئة وشهر؛ ليست معاملة أو حساب احتياطي. |
| Category | الفئة | سبب النشاط المالي. |
| Counterparty | الطرف الآخر | الشخص أو الجهة أو الحساب في الطرف الآخر من المعاملة. |
| Held for | مملوك لـ | المالك الفعلي للقيمة إذا لم تكن للمستخدم. |
| Name | الاسم | تسمية مقروءة تظهر للمستخدم. |
| Code | الرمز | معرّف تقني ثابت للبحث والربط. |
| ID | المعرّف | مفتاح داخلي لا يحمل معنى للمستخدم. |
| Date | التاريخ | يوم انتقال المال. |
| As of | كما في | التاريخ الذي تصف القيمة أو السعر حالته. |
| Amount | المبلغ | قيمة المال المنقول بعملة الحساب. |
| Units | الوحدات | عدد الأسهم أو وحدات الصندوق أو القطع أو الغرامات. |
| Notes | ملاحظات | نص حر مرتبط بالسجل. |
| Due date | تاريخ الاستحقاق | موعد الدفعة المجدولة. |
| Sale factor | معامل البيع | الحصة المتوقعة من قيمة الفئة عند البيع اليوم. |
| Carryover | المبلغ المرحّل | الجزء غير المستخدم من الميزانية الذي ينتقل للشهر التالي؛ مش فلوس محجوزة. |
| Financial health | صحتك المالية | عرض للقيَم المالية وفتراتها ومقارنتها بالحدود الشخصية، بلا درجة مركبة. |

### سلطة الأجهزة

| English | العربية | المعنى |
|---|---|---|
| Home node / Home | الجهاز الرئيسي | الجهاز الذي يعتمد قاعدة البيانات أو يراجع التعديلات وينشر النتائج. |
| Borrower | الجهاز المستعير | جهاز مقترن يحصل مؤقتاً على صلاحية الكتابة. |
| Checkout | إعارة الصلاحية | منح مؤقت لصلاحية الكتابة بمعرّف فريد. |
| Checkpoint | نقطة تحقق | نسخة مشفرة ثابتة ومتحقق منها من قاعدة البيانات. |
| Lend | إعارة | تسجيل الجهاز الرئيسي للمنح والتحول إلى القراءة فقط. |
| Hand back | إعادة | تجميد نسخة المستعير وإرسالها للتحقق والنشر. |
| Received | مستلَم | وصول النسخة كاملة إلى الجهاز الرئيسي مع بقاء الكتابة متوقفة. |
| Accepted | مقبول | تحقق الجهاز الرئيسي من النسخة ونشرها وإصدار إيصال دائم. |
| Proposal | مقترح | طلب موقع وثابت لتنفيذ إجراء واحد. |
| Pending edit | تعديل معلّق | مقترح محفوظ محلياً ينتظر قرار الجهاز الرئيسي ولا يدخل التقارير المؤكدة. |
| Confirmed change | تغيير مؤكد | نتيجة مقبولة ودائمة يعاد نسخها كما هي. |
| Decision receipt | إيصال القرار | نتيجة دائمة مرتبطة بهوية المقترح ومحتواه. |
| Outbox | صندوق الصادر | طابور مشفر دائم على الجهاز. |

### الفئات والأنواع

| English | العربية | المقصود |
|---|---|---|
| L1 — Activity family | المستوى الأول — عائلة النشاط | |
| L2 — Broad category | المستوى الثاني — الفئة العامة | |
| L3 — Detail | المستوى الثالث — التفصيل | |
| Personal | شخصي | |
| Work | عمل | |
| Investment | استثمار | |
| Opening | رصيد افتتاحي | |
| Inflow | إيداع / وارد | |
| Outflow | سحب / صادر | |
| Internal-account transfer | تحويل بين الحسابات | |
| Investment buy / sell | شراء / بيع استثماري | |
| Dividend | توزيعات | |
| Valuation | تقييم | |
| Reconciliation adjustment | تسوية مطابقة | |
| Conversion | تحويل عملة | |
| Physical item | مقتنى مادي | أصل ملموس متعقب بالعدد والوزن والتكلفة والتقييم. |
| Net gold weight | الوزن الصافي للذهب | وزن السبيكة الذهبية في القطعة دون الأحجار أو الأجزاء غير الذهبية. |
| Fine-gold exposure | التعرّض للذهب الخالص | مكافئ الذهب الخالص المحسوب للتوزيع والتقارير. |
| Acquisition cost | تكلفة الاقتناء | إجمالي ما دُفع للكمية المقتناة، شاملاً المصنعية والرسوم عند وجودها. |
| Manual item valuation | تقييم يدوي للمقتنى | قيمة مؤرخة يُدخلها المستخدم عند عدم ملاءمة السعر المشترك. |
| Confirmed alias | اسم بديل مؤكد | تهجئة بديلة وافق عليها المستخدم للاسم المعتمد. |
| Search suggestion | اقتراح بحث | تطابق محتمل يُعرض للمراجعة ولا يختار الهوية تلقائياً. |
| Privacy mode | وضع الخصوصية | تمويه المبالغ الظاهرة مع إبقاء النسب والتواريخ والأسماء مقروءة. |

### مصطلحات إضافية وإدخال البيانات

| English | العربية | المعنى |
|---|---|---|
| Amount input | إدخال المبلغ | اكتب رقماً أو عملية حسابية؛ راجع الناتج قبل الحفظ. |
| Amount set aside | المبلغ المحجوز | نقد مخصص للاحتياطي ويظل في الحساب. |
| Authority generation | جيل السلطة | تاريخ صلاحية الجهاز الرئيسي؛ استبداله الصريح يبدأ جيلاً جديداً. |
| Base budget | الميزانية الأساسية | مبلغ الخطة الشهرية للفئة قبل إضافة أي ترحيل. |
| Budget carryover | ترحيل الميزانية | مساحة إنفاق غير مستخدمة تُضاف للشهر التالي، من غير حجز نقد. |
| CD terms | شروط شهادة الإيداع | شروط الاستحقاق والسحب المبكر للشهادة. |
| Cash account | حساب النقد | الحساب الذي يدفع أو يستقبل نقد الصفقة. |
| Cash forecast | توقع النقد | تقدير النقد وفق المواعيد والمدفوعات والخطة. |
| Cash planning | تخطيط النقد | تقدير ما يمكن إنفاقه مع مراعاة الالتزامات والاحتياطيات. |
| Change ownership | تغيير الملكية | تحديث المالك الفعلي للقيمة المسجلة. |
| Confirmed cursor | مؤشر التأكيد | جيل السلطة ورقم القرار وبصمة التثبيت التي تحدد التقدم المتصل. |
| Cost basis / average cost | أساس التكلفة / متوسط التكلفة | تكلفة الوحدات المحتفظ بها، شاملة الرسوم. |
| Date input | إدخال التاريخ | يقبل صيغ التاريخ المحددة ويخزنها بصيغة معيارية. |
| Earliest withdrawal date | أقرب تاريخ للسحب | أول يوم يمكن فيه سحب الوديعة وفق شروطها. |
| Exchange | البورصة | السوق المسجل برمز MIC ويظهر باسمه الشائع. |
| Expense paid for you | مصروف دُفع نيابةً عنك | معاملة تحملها طرف آخر عن المستخدم. |
| Fees | الرسوم | تكاليف الصفقة؛ وضّح هل هي ضمن المبلغ أو خارجه. |
| Field group | مجموعة حقول | حقول يجب التحقق منها وتحديثها معاً للحفاظ على معنى الإجراء. |
| Financial health limit | حد الصحة المالية | تفضيل شخصي لمقارنة رقم مالي بحد أدنى أو أقصى. |
| ISIN | رقم ISIN | معرّف عالمي اختياري للأوراق المالية. |
| Karat-specific gold price | سعر الذهب حسب العيار | سعر غرام السبيكة من العيار المحدد؛ لا تعدّل السعر بالنقاوة مرة أخرى. |
| Last due date | آخر تاريخ استحقاق | موعد آخر دفعة متكررة. |
| Ledger line / journal line | قيد السجل / قيد اليومية | أثر المعاملة على حساب وأصل مالي. |
| Ledger-line reference | مرجع القيد | مرجع المعاملة مضافاً إليه رقم القيد. |
| Linked (import row) | مرتبط (صف مستورد) | صف كشف مربوط بمعاملة موجودة كي لا تُسجل مرتين. |
| Market key | مفتاح السوق | المعرّف الثابت للأداة في ملف الأسعار. |
| Money in | فلوس داخلة | قيمة دخلت إلى الحساب. |
| Money out | فلوس خارجة | قيمة خرجت من الحساب. |
| Monthly base budget | الميزانية الشهرية الأساسية | خطة الفئة للشهر قبل الترحيل. |
| Observed-month average | متوسط الأشهر المسجلة | متوسط إنفاق الأشهر التي لها نشاط مؤهل فقط؛ الشهر بلا حركة لا يُحسب صفراً. |
| Opening adjustment | تسوية افتتاحية | تعديل يطابق الرصيد الافتتاحي المسجل. |
| Origin incarnation | دورة منشأ الجهاز | مساحة تسلسل خاصة بتثبيت الجهاز وتتجدد عند تعذر إثبات استمرارية العداد بأمان. |
| Owner ID | معرّف المالك | مرجع اختياري للطرف الذي يملك القيمة فعلياً. |
| Payment status | حالة الدفع | يوضح هل سُدد الموعد أم لا. |
| Payments left / Number of payments | الدفعات المتبقية / عدد الدفعات | عدد دفعات القرض محسوباً من أول استحقاق. |
| Price file | ملف الأسعار | أسعار الإغلاق لسوق محدد في حزمة محدثة. |
| Realized / unrealized return | عائد محقق / غير محقق | ربح البيع المنفذ / تغير قيمة الوحدات المحتفظ بها. |
| Recurring item | بند متكرر | فاتورة أو دخل أو دفعة مجدولة بتكرار محدد. |
| Reevaluation ledger | سجل إعادة التقييم | تفاصيل العائد الشهري وإعادة تقييم الاستثمار. |
| Revaluation | إعادة تقييم | تحديث قيمة الأصل حسب السعر في تاريخ معين. |
| Rule | قاعدة | شروط تلقائية لتصنيف المعاملات أو تقسيمها؛ لا تغير الماضي إلا بطلب المستخدم. |
| Saving needed | المطلوب ادخاره | المبلغ المطلوب لتغطية هدف الادخار في الفترة المختارة. |
| System-generated posting | قيد ينشئه النظام | حركة يولدها النظام لأغراض التقييم أو المطابقة. |
| Tag | وسم | كلمة مسبوقة بعلامة # لربط المعاملات في البحث والملاحظات. |
| Target amount | المبلغ المستهدف | القيمة التي يدخر الاحتياطي للوصول إليها. |
| Ticker / symbol | رمز التداول | الرمز العام للأداة في السوق. |
| Transaction reference (ref) | مرجع المعاملة | معرّف مقروء وثابت للمعاملة. |
| Type | النوع | تصنيف سجل أو معاملة. |
| Update prices | تحديث الأسعار | جلب أحدث الأسعار وأسعار نهايات الشهور الناقصة للمراكز المحتفظ بها. |
| Value | القيمة | قيمة أصل أو بند في تاريخ «كما في». |
| Void / delete | إلغاء / حذف | تصحيح قابل للاسترجاع يستبعد المعاملة من الأرصدة النشطة مع إبقاء تاريخها. |
| XIRR | العائد السنوي الداخلي | عائد سنوي محسوب لتدفقات نقدية بتواريخ مختلفة. |

### التصنيفات والحسابات والأصول

الفئات تشرح سبب النشاط: **شخصي** ثم فئة عامة مثل الطعام والبقالة؛ **عمل** مثل الراتب؛ و**استثمار** مثل التوزيعات. المستوى الثالث للتفاصيل متروك فارغاً حالياً ولا يُضاف مسبقاً. لا تقسم الفئات إلى شجرتي دخل ومصروف؛ اختَر النشاط الذي يشرح المعاملة حتى لو كانت استرداداً. الحساب يشرح أين توجد القيمة، وفئة الأصل تشرح نوعها. من أنواع الأصول المدعومة: النقد والعملات، الأسهم، الصناديق، الذهب المادي، والودائع أو شهادات الإيداع. ومن أنواع الحسابات: محفظة نقدية، حساب بنك، وديعة، وساطة، ومكان أصل مادي.

### أسماء الأرقام المعروضة

الجدول التالي يغطي كل الأرقام المسجلة في `lightning/core/figures.py`. العمود الإنجليزي يطابق الجدول المولّد أعلاه؛ وأسماء الدوال وصيغ المصدر التفصيلية تظل في ذلك الجدول.

| English figure | التسمية العربية | المعنى وطريقة الحساب |
|---|---|---|
| In your accounts | في حساباتك | إجمالي القيمة الموجودة في حساباتك، بما فيها فلوس وأصول غيرك. الحساب: اللي تملكه + أموال لغيرك. |
| Held for others | أموال لغيرك | فلوس ووحدات في حساباتك لكنها مملوكة لناس تانية؛ قراءة مباشرة من السجل. |
| What you own | اللي تملكه | قيمة كل ما تملكه في حساباتك. الحساب: النقدية اللي تملكها + قيمة الاستثمارات + أصول تانية تملكها. |
| Bank and wallet cash | نقدية البنك والمحفظة | النقد الموجود في الحسابات البنكية والمحافظ؛ قراءة مباشرة من السجل. |
| Brokerage cash | نقدية الاستثمار | النقد غير المستثمر الموجود في حسابات الوساطة؛ قراءة مباشرة من السجل. |
| Cash you own | النقدية اللي تملكها | نقد البنوك والمحافظ مضافاً إليه النقد في حسابات الوساطة. |
| Deposits | الودائع والشهادات | قيمة الودائع والشهادات حسب رصيدها؛ تدخل ضمن قيمة الاستثمارات. |
| Holdings value | قيمة الاستثمارات | أحدث قيمة لكل ما تملكه غير النقد: شهادات وودائع وأسهم وصناديق وذهب وأصول أخرى. |
| Other you own | أصول تانية تملكها | ما تملكه بخلاف النقد والاستثمارات. الحساب: اللي تملكه − النقدية اللي تملكها − قيمة الاستثمارات. |
| Reserves | المبالغ المحجوزة | مبالغ للطوارئ والأهداف المؤرخة، بعد خصم ما استُخدم منها في مدفوعات مرتبطة. تظل ضمن حساباتك وممتلكاتك؛ تُقرأ من الخطة. |
| Bills due | فواتير مستحقة | فواتير واشتراكات وأقساط قروض حل موعدها أو فات، ولسه ما اتدفعتش. |
| Loans still to pay | قروض لسه عليك | كل دفعات القروض اللي لسه ما اتدفعتش، سواء مستحقة أو جاية. |
| What you owe | اللي عليك | المدفوعات المؤكدة: الفواتير المستحقة (من غير قسط القرض) + أقساط القروض المتبقية. |
| Net worth | صافي ثروتك | اللي تملكه − اللي عليك. |
| Bills and subscriptions a month | الفواتير والاشتراكات شهريًا | تكلفتها الشهرية؛ الأسبوعي يُحسب 52 مرة في السنة والسنوي مرة، والمدفوع لمرة واحدة لا يدخل. |
| Loan payments a month | أقساط القروض شهريًا | قيمة أقساط القروض شهرياً، للقروض التي بقيت لها دفعات. |
| Debt to net worth | الديون مقارنة بصافي ثروتك | اللي عليك ÷ صافي ثروتك؛ غير متاح لو صافي الثروة صفر أو أقل. |
| Debt to cash | الديون مقارنة بالنقدية | اللي عليك ÷ النقدية اللي تملكها؛ يوضح إن كان النقد يكفي لسداد الدين. |
| Loan payments to income | أقساط القروض من دخلك | أقساط القروض شهريًا ÷ متوسط الدخل الشهري. |
| Fixed costs to income | المصاريف الثابتة من دخلك | (الفواتير والاشتراكات شهريًا + أقساط القروض شهريًا) ÷ متوسط الدخل الشهري. |
| Free cash | النقدية المتاحة | النقدية اللي تملكها − المبالغ المحجوزة − الفواتير المستحقة. |
| Portfolio value | قيمة المحفظة | تساوي قيمة الاستثمارات؛ تشمل كل ما تملكه غير النقد. نقد الوساطة داخل النقدية اللي تملكها. |
| Holdings after sale (estimate) | قيمة الاستثمارات بعد البيع (تقديري) | مجموع قيمة كل فئة × معامل بيعها. شهادة الإيداع قبل موعد السحب المبكر = صفر؛ بعده تُحسب بمعامل فئتها، وعند الاستحقاق برصيدها الكامل. |
| If you sold today (estimate) | لو بعت النهارده (تقديري) | النقدية المتاحة + قيمة الاستثمارات بعد البيع التقديرية. |
| Money in | فلوس داخلة | الدخل المسجل خلال الفترة. لا يشمل التحويلات أو الصفقات أو الأموال المملوكة لغيرك. |
| Money out | فلوس خارجة | الإنفاق المسجل خلال الفترة بعد الاستردادات. لا يشمل التحويلات أو الصفقات أو الأموال المملوكة لغيرك. |
| Net flow | صافي التدفق | الفلوس الداخلة − الفلوس الخارجة. |
| Savings rate | نسبة الادخار | صافي التدفق ÷ الفلوس الداخلة. لو الإنفاق تجاوز ضعفي الداخل، تُعرض الفجوة بالكلام بدل نسبة أقل من −100%. |
| Opening balances in the period | الأرصدة الافتتاحية خلال الفترة | فلوس وأصول سجلتها على إنها ملكك بالفعل خلال الفترة؛ مش زيادة جديدة لأنك كنت تملكها قبلها. |
| Change in what you own | التغير في اللي تملكه | قيمة ما تملكه في نهاية الفترة − قيمته في اليوم السابق لبدايتها − أرصدة بداية الفترة. |
| Change in net worth | التغير في صافي ثروتك | صافي الثروة في نهاية الفترة − صافيها في اليوم السابق لبدايتها − أرصدة بداية الفترة. |
| Per month | شهريًا | الإنفاق خلال الفترة ÷ عدد الشهور التقويمية التي تغطيها. |
| Usual month | الشهر المعتاد | متوسط الإنفاق في آخر ستة شهور كاملة قبل الفترة. |
| Usual range | النطاق المعتاد | أقل ووسط وأعلى إنفاق شهري في الاثني عشر شهراً الكاملين قبل الفترة؛ يحتاج ثلاثة أشهر على الأقل. |
| Investing rate | نسبة الاستثمار | الأموال المضافة للاستثمار ÷ الفلوس الداخلة؛ لا تزيد عن نسبة الادخار. |
| Average monthly income | متوسط الدخل الشهري | متوسط دخل الفئات المختارة خلال آخر 3 أو 6 شهور مكتملة. الشهر بلا راتب يُحسب صفرًا بعد بدء الدخل، وتُتجاوز الشهور السابقة لأول راتب. قبل أول شهر مكتمل، يستخدم الدخل المسجل في المتكرر. |
| Average monthly spending | متوسط المصروفات الشهرية | متوسط الإنفاق في فئات الميزانية خلال نفس 3 أو 6 شهور المكتملة؛ الاستثمارات والفئات لمرة واحدة خارج الحساب. يمكن إدخال صندوق الطوارئ. |
| Base budget | الميزانية الأساسية | المبلغ الناتج عن قاعدة الميزانية: مبلغ ثابت أو نسبة من الدخل أو متوسط إنفاق. |
| Carryover | المبلغ المرحّل | المتبقي في خطة الشهر الماضي، إذا كان الترحيل مفعلاً. |
| Planned | المخطط | الميزانية الأساسية + المبلغ المرحّل. الإجمالي قد يشمل تقديرات خلفية للفئات غير المتتبعة. |
| Spent | المنفق | الفلوس الخارجة المسجلة في الفئة خلال الشهر. |
| Left in plan | المتبقي في الخطة | المخطط − المنفق. الفئات لمرة واحدة لا تدخل في المنفق. |
| Plan leaves to save | المتبقي للادخار من الخطة | متوسط الدخل الشهري − المخطط. |
| Planned savings rate | نسبة الادخار المخططة | المتبقي للادخار من الخطة ÷ متوسط الدخل الشهري. |
| Savings target | هدف الادخار | متوسط الدخل الشهري × حد نسبة الادخار الذي حددته. |
| Emergency fund top-up | زيادة صندوق الطوارئ | النقص اللازم للوصول لصندوق يغطي ستة أشهر، موزع على سنتين؛ صفر لما يكتمل الصندوق. |
| Saving needed | المطلوب ادخاره | الأكبر بين هدف الادخار وبين الادخار للأهداف + زيادة صندوق الطوارئ. |
| Most you can plan | أقصى مبلغ تقدر تخطط له | متوسط الدخل الشهري − المطلوب ادخاره. |
| Cost | التكلفة | إجمالي ما دفعته للوحدات التي لا تزال تملكها؛ قراءة مباشرة من السجل. |
| Unrealized gain | ربح غير محقق | قيمة الاستثمارات − التكلفة. |
| Price change on what you hold | تغير قيمة المقتنيات | الربح غير المحقق في نهاية الفترة − الربح غير المحقق في بدايتها. |
| Gain from sales | أرباح البيع | حصيلة البيع − تكلفة الوحدات المباعة؛ قراءة مباشرة من السجل. |
| Dividends and interest | توزيعات وفوائد | التوزيعات والفوائد التي استلمتها؛ قراءة مباشرة من السجل. |
| Net gain or loss | صافي الربح أو الخسارة | أرباح البيع + تغير قيمة المقتنيات + التوزيعات والفوائد. |
| Money added | فلوس مضافة | النقد المنقول لحسابات الاستثمار من خارجها − النقد المسحوب منها للخارج. |
| Typical move | الحركة المعتادة | الانحراف المعياري لتغيرات السعر الشهرية بعد توفر ثلاثة أشهر على الأقل. |
| Fall from its high | الانخفاض من أعلى قيمة | النسبة التي يقل بها سعر نهاية الشهر عن أعلى سعر نهاية شهر سابق. |
| Average cost | متوسط التكلفة | التكلفة ÷ عدد الوحدات التي لا تزال تملكها؛ الرسوم محسوبة ضمن التكلفة. |
| Growth | النمو | صافي الربح أو الخسارة ÷ (قيمة المحفظة في بداية الفترة + الفلوس المضافة). |
| Safe to spend | المتاح الآمن للصرف | تقدير: النقدية المتاحة − الفواتير والأقساط قبل الدخل القادم − المتبقي للإنفاق من الميزانية − الادخار للأهداف − زيادة صندوق الطوارئ − باقي هدف الادخار. |
| Bills inside the plan | الفواتير ضمن الخطة | فواتير الشهر المستحقة أو القادمة في فئة لها ميزانية؛ محسوبة داخل ميزانيتها. |
| Budget left to spend | المتبقي من الميزانية للصرف | المتبقي في الخطة − الفواتير المدرجة فيها، لتجنب حساب الفاتورة مرتين. |
| Bills and loan payments before next income | الفواتير والأقساط قبل الدخل القادم | الفواتير والاشتراكات وأقساط القروض المجدولة حتى موعد الدخل القادم، ما لم يحن موعدها بعد. |
| Saving for goals | الادخار للأهداف | احتياج الأهداف المؤرخة المتبقي موزعاً على الشهور الباقية. |
| Rest of savings target | باقي هدف الادخار | هدف الادخار − الادخار للأهداف − زيادة صندوق الطوارئ، بحد أدنى صفر. |

### مصطلحات إضافية من النص الإنجليزي

| English | العربية | المقصود |
|---|---|---|
| Activity | النشاط | السبب العام للحركة، بعيدًا عن اتجاه الفلوس. |
| Loan | قرض | خطة أقساط تسجل الدفعة وقت سدادها. |
| Reserve | مبلغ محجوز | جزء من الفلوس المملوكة متعين لهدف؛ التعيين نفسه مش حركة مالية. |
| Opening balance | رصيد افتتاحي | الرصيد وقت بدء المتابعة؛ مش دخل جديد. |
| Unit | وحدة | كمية من أصل زي سهم أو وحدة صندوق. |
| Paid | مدفوع | دفعة اتسددت بمعاملة مسجلة. |
| Skipped | متخطّى | دفعة قال المستخدم إنها مش هتحصل. |
| Due | مستحق | موعد الدفعة جه ولسه ما اتسددتش. |
| Upcoming | قادم | موعد الدفعة لسه ما جاش. |
| From | من | أول تاريخ في الفترة المختارة. |
| Function | دالة الحساب | اسم الوظيفة البرمجية التي تحسب الرقم؛ مش تسمية على الشاشة. |
| L1 — Activity family | المستوى الأول — عائلة النشاط | أوسع مستوى للفئة. |
| L2 — Broad category | المستوى الثاني — الفئة العامة | فئة تحت عائلة النشاط. |
| L3 — Detail | المستوى الثالث — التفصيل | تفصيل اختياري تحت الفئة العامة. |
