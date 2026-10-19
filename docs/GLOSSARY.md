Last reviewed 2026-10-13 · app 1.0.0b1

# Glossary

One name and one meaning per term and figure. How things are built is in [Architecture](ARCHITECTURE.md), the product story in [Project Overview](PROJECT_OVERVIEW.md), history in `CHANGELOG.md`, the look in the [guideline](../guideline/). The figures tables are generated from `lightning/core/figures.py` (`python -m lightning.core.figures`); change a figure there, never here.

## Contents

Find a term: `grep -n -i '<term>' docs/GLOSSARY.md`.

| Section | When to read |
|---|---|
| Device authority | Lending write access |
| The basic model | Any core noun |
| Three layers: ledger, plan, report | What a layer may do |
| Reported figures: one name, one calculation, one function | A figure's formula or function |
| Category taxonomy (why the activity happened) | Category levels |
| Names and identifiers | Name, code, ID; input rules |
| Asset and account taxonomy (what vs where) | Account kinds, code patterns |
| Transaction and posting types | The ten type codes |
| العربية — المسرد العربي | Egyptian Arabic names |

## Device authority

Built v1 lending; planned replacement: [edit journal](../issues/4-edit-journal-and-devices/4A-edit-journal.md).

| Term | Meaning |
|---|---|
| **Home node** | The device holding the accepted database and deciding which device may write. The phone is the intended default. |
| **Borrower** | A paired device (initially a PC) holding temporary write authority for one checkout. |
| **Checkout** | One grant of write authority, with a random checkout ID and increasing home epoch. |
| **Checkpoint** | An immutable, verified encrypted database version with an ID and ciphertext hash. |
| **Lend / Received** | Home goes read-only and records a grant before the borrower writes / home durably holds the complete returned candidate and has not resumed writing. |
| **Hand back** | Borrower freezes its copy and returns an encrypted candidate for home to verify and publish. |
| **Accepted** | Home verified and published the candidate and issued a durable receipt for the new checkpoint. |

## The basic model

**Instalment purchase (taqseet):** a loan plan for an outstanding purchase price plus any financed fee, with an exact final instalment. Creating it records no cash.

**Early loan payment:** actual extra cash paid to reduce an existing loan, clearing overdue amounts first and then shortening its end. A settlement fee is spending and does not reduce principal.

Layer: **Ledger** (real money moved), **Plan** (what-if, moves nothing) or **Report** (reads both).

| Term | Layer | Meaning |
|---|---|---|
| **Account** | Ledger | Where value is held (CIB, Cash wallet, THNDR brokerage). |
| **Adjust balance** | Set an account to a balance you know on a date; the difference is recorded as one adjustment row. Was "Check against bank". CDs and physical items say **Update value** instead. | Read directly from the ledger | `reconciliation.ReconciliationService.adjust` |
| **Payday** | The day of the month your salary usually arrives (1-31; 29-31 mean the last day of a shorter month). Lightning expects the salary then in the cash plan and forecast; it records nothing until the money arrives. Shown as "Salary arrives on day N of each month". | Read directly from the salary setup | `planning` salary setup |
| **Gam'eya** | Ledger | A rotating savings circle: one account per circle; every instalment and your payout is an internal transfer, never income or spending; balance = paid in − received (positive: Gam'eya paid in; negative: Gam'eya still to pay). |
| **Financial asset** | Ledger | What an account holds or counts (EGP cash, COMI share, fund unit, CD, gold gram). |
| **Asset class** | Ledger | The kind of wealth an asset is; not where held or why paid. |
| **Exposure** | Ledger | What an asset economically tracks, apart from its class (a gold fund is a Fund with Gold exposure). |
| **Holding / position** | Ledger | Calculated quantity of one asset in one account at a date. |
| **Balance** | Ledger | Calculated value or quantity of an account or position at a date; never typed in. |
| **Physical item** | Ledger | A named tangible asset tracked by pieces, net gold weight, karat, cost and valuation; not a security. |
| **Net gold weight** | Ledger | Grams of gold alloy per piece, excluding stones. Fine-gold exposure = pieces × net grams × karat/24; the karat-specific price applies to alloy grams, never adjusted again. Manual item valuation is a user-entered dated value. |
| **Acquisition cost** | Ledger | Total paid for the item's current quantity, including workmanship and fees; price updates never change it. |
| **Worn** | Ledger | A flag on a physical gold piece: gold you wear. Zakat counts it only if the setting is on. |
| **Zakat day** | Plan | The date the user picked once for counting zakat; each next one is 354 days later (a lunar year). Hijri dates are not built. |
| **Zakat category** | Ledger | The system spending category `EXP.SYSTEM.ZAKAT`; zakat paid is ordinary spending in it and lowers Still to pay for its zakat year. |
| **Category** | Ledger | Label for the activity behind a transaction; never describes counterparty, account or asset. |
| **Counterparty** | Ledger | The person, business, institution or own account on the other side; up to ten confirmed aliases each; typo matches are only suggestions. |
| **Transaction** | Ledger | A dated user or system event in the main ledger. |
| **Main ledger** | Ledger | The single ledger every register, budget actual and report is derived from. |
| **Profile currency** | Ledger + Report | Currency of ledger amounts and report totals; fixed once history exists. |
| **FX revaluation** | Ledger + Report | Month-end change in the profile-currency value of foreign cash held; changes no units, is not income or spending. |
| **Owner ID** | Ledger | Optional Counterparty on a line, shown as **Held for**; blank means the user owns it. |
| **Held for** | Ledger | Who owns money or units in the user's account when not the user; separate from Counterparty (formerly Whom / Owned by / Owner). |
| **Change ownership** | Ledger | Zero-sum entry moving part of an account's balance between the user and one saved person. |
| **Expense paid for you** | Ledger | An expense another person paid, recorded as the user's and paired with equal custody for the payer; gross cash unchanged. |
| **Money in / money out** | Ledger | Direction value crosses an account boundary; direction never decides category. |
| **Transfer** | Ledger | Value moved between the user's own accounts; not income or expense. |
| **Investment trade** | Ledger | Brokerage cash for units (buy) or units for cash (sell), entered in that brokerage's register. |
| **Opening balance** | Ledger | Separately dated entry for an account's value at a chosen point; earlier transactions may still be added. |
| **Revaluation** | Ledger | Change in investment value from price, not deposits or withdrawals. |
| **Reevaluation ledger** | Ledger | Monthly per-account, per-asset units, prices, values and returns; each account total is one system-generated `VAL` journal in the main ledger. |
| **Void / delete** | Ledger | Recoverable correction: leaves active balances, keeps history. |
| **Linked (import row)** | Ledger | A statement row tied to an already recorded transaction instead of posting again; moves no money. |
| **Realized / unrealized return** | Report | Gain from units sold / change in value of units held. |
| **XIRR** | Report | Annualized money-weighted return from dated cash flows and an ending value; unavailable results need an explanation. |
| **Financial health** | Report | Read-only profile of named figures, periods and personal-limit comparisons; no score. |
| **Financial health limit** | Report | Profile-owned minimum (passes at or above) or maximum (at or below) for a figure; unavailable figures get no judgement. |
| **Budget** | Plan | Planned spending for a category and month; not a reserve or a transaction. |
| **Monthly base budget** | Plan | A category's monthly plan before carryover: fixed EGP, a percentage of Average monthly income, or an observed-month average. Shown as **Base budget**. |
| **Observed-month average** | Plan | 3m/6m spending divided by the months with qualifying activity; empty months are not zero. |
| **Budget carryover** | Plan | Optional unused room added to a later month's limit; sets aside no cash and does not reduce free cash. |
| **Reserve** | Plan | Already-owned cash assigned to an emergency fund or goal; moves no money, does not change net worth. |
| **Emergency fund** | Plan | The permanent reserve section. Coverage = emergency Reserves ÷ Average monthly income (or spending, per Settings › Budget), in months; aim six. |
| **Cash planning** | Plan | Tab for spendable cash and commitments: Plan, Recurring, Loans, Reserves. Posts nothing by itself. |
| **Recurring item** | Plan | Bill, subscription or income repeating weekly, monthly, every 3 months, yearly or once. |
| **Loan** | Plan | Entered as its payments (amount, next date, payments left, optional amount borrowed). Each payment is spending when paid (System Categories › Loan payments unless changed); paying lowers cash, spending room and loans still to pay together, so net worth is unchanged. |
| **Payment status** | Plan | **Paid** (a posted transaction settles it), **Skipped**, **Due** (today or earlier, unsettled) or **Upcoming**; voiding the transaction makes it Due again. |
| **Cash forecast** | Plan | Free cash carried month by month with scheduled payments, projected CD proceeds and savings lines. Changes neither net worth nor free cash. |
| **Scheduled cash checks** | Plan | Dated day-end checks of owned cash after scheduled payments and projected deposit/circle cash. Flags total and individual-account shortages. Includes reserved cash; excludes variable spending, savings goals and overdue income. Changes no balance. |
| **CD terms** | Plan | Start, earliest withdrawal, maturity, principal, rate, simple payout or compounding, destination. Forecast cash, never post it. |
| **Sale factor** | Plan | 0-100% estimate of what an asset class fetches if sold today; 95% if unset. Feeds Holdings after sale and If you sold today. A CD uses it only after its earliest withdrawal date (first date it can be redeemed early), 100% at maturity. Formerly *liquidation factor*. |

| **Action history** | Plan | Up to twenty undo/redo action groups in the current database connection; nested changes and links replay together, with stale-state checks. Expires when the profile/session closes; not backed up. |
| **Checked history** | Ledger | Bank-confirmed cash balance/date protecting that account’s earlier ledger rows and headers. Corrections require explicit unlock. |
| **Activity review** | Plan | One transaction and its source evidence, category, planned settlement, reserve use and reimbursement actions. Linking never posts it again. |
| **Reimbursement claim** | Plan | An explicit amount expected back for an existing owned expense. Outstanding = the eligible claimed amount minus valid explicitly linked receipts; not cash before receipt. |
| **Saved view** | Report | Named account/category/search/tag filters with live date presets or a custom range; reused by register, summary report and CSV export. |
| **Weekly review** | Plan | A completion flow over existing Needs you decisions. Recording a review keeps unresolved items visible; optional reminders require an unlocked session. |

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
| **Gam'eya paid in** | What you have paid into your savings circles and not yet taken out: a circle's balance while it owes you. It is part of Holdings value, a circle cannot be sold early (100%). | Read directly from the ledger | `planning.position.Position.gameya_paid_in` |
| **Holdings value** | Everything you own that is not cash, at its latest value: certificates and deposits, Gam'eya paid in, stocks, funds, gold and other assets. Assets that are not cash sit under one roof (owner decision 2026-10-04). | Read directly from the ledger | `planning.position.Position.holdings_value` |
| **Other you own** | Anything you own that is neither cash nor a holding. | What you own − Cash you own − Holdings value | `planning.position.Position.other_you_own` |
| **Gam'eya still to pay** | What you owe a savings circle you took the pot from early: its balance while it is below zero. Net worth does not change when you take the pot. | Read directly from the ledger | `planning.position.Position.gameya_still_to_pay` |
| **Kept apart** | Cash you own that is not ready to spend: cash in a brokerage, cash in another currency, or an account you set apart. It stays in what you own and in If you sold today. | Read directly from the ledger | `reporting.service.ReportingService.owned_cash_kept_apart` |
| **Portfolio value** | Holdings value under the name the Investments tab uses: everything you own that is not cash. Cash waiting in a brokerage account counts in Cash you own (owner decisions 2026-10-04). | Holdings value | `planning.position.Position.portfolio_value` |
| **Shares and funds** | Your stocks and funds at their latest value, counted in full for zakat. | Read directly from the ledger | `zakat.ZakatService.assess` |
| **Gold held as savings** | Your gold pieces and gold by the gram that you keep as savings, at the gold price. Pieces marked as worn are left out. | Read directly from the ledger | `zakat.ZakatService.assess` |
| **Gold you wear** | Your gold pieces marked as worn. Zakat counts them only if you turn that on. | Read directly from the ledger | `zakat.ZakatService.assess` |
| **Gam'eya instalments due now** | Instalments dated today or earlier and not yet recorded, on a savings circle you took the pot from early. Zakat takes them off with the debts due now. | Read directly from the ledger | `zakat.ZakatService.gameya_due_now` |
| **Nisab** | The least wealth zakat applies to: 85 g of 24K gold at the gold price of the day, or the amount you typed when there is no gold price. | Read directly from the ledger | `zakat.ZakatService.nisab` |
| **Zakat rate** | The share of zakatable wealth that is due: 2.5% by the common rule. | Read directly from the ledger | `zakat.ZAKAT_RATE` |
| **Paid this zakat year** | What you spent in the Zakat category since your last zakat day, up to the next. | Read directly from the ledger | `zakat.ZakatService.paid_between` |
| **Money in** | Your posted income in the period. Transfers, trades and money held for others are left out. | Read directly from the ledger | `reporting.service.CashFlow.inflows` |
| **Money out** | Your posted spending in the period, after refunds. Transfers, trades and money held for others are left out. | Read directly from the ledger | `reporting.service.CashFlow.outflows` |
| **Net flow** | What was left of money in after money out. | Money in − Money out | `reporting.service.CashFlow.net` |
| **Savings rate** | The share of money in that you kept. When money out is more than twice money in (below −100%, such as a month whose pay came early), the Overview and Financial health say the gap in words instead. | Net flow ÷ Money in | `reporting.service.CashFlow.savings_rate` |
| **Opening balances in the period** | Money and assets you recorded as already yours (opening balances and existing holdings) during the period. They were yours before, so they are not a change. | Read directly from the ledger | `reporting.service.ReportingService.opening_balances_between` |
| **Change in what you own** | How much what you own grew or shrank in the period. | What you own at the end − What you own the day before the start − Opening balances in the period | `planning.position.PositionService.change_in_what_you_own` |
| **Per month** | A period's money out divided by the calendar months it covers, so a year to date compares with a single month. | Read directly from the ledger | `reporting.spending.spending_profile` |
| **Usual month** | The average money out of the last six earlier months, using matching calendar days for a partial period. | Read directly from the ledger | `reporting.spending._against_history` |
| **Usual range** | The lowest, middle and highest money out of the twelve earlier months, using matching calendar days for a partial period. It needs three of them. | Read directly from the ledger | `reporting.spending._against_history` |
| **Investing rate** | The share of what you kept (net flow) that you moved into investments. Money from earlier savings does not count, so it is never more than 100%. | Money added ÷ Net flow | `investments.report.investing_rate` |
| **Average monthly income** | Income in your chosen income categories, averaged over the last 3 or 6 completed months that had any (Settings › Budget). Until a completed month has income, the income set up in Recurring stands in. The budget, reserves and the cash forecast all use it. | Read directly from the ledger | `budgeting.service.BudgetService.income_average` |
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
| **Average rate** | What each unit of a foreign currency you still hold cost you, in the profile currency: conversions count at the rate you got, money in at the day's rate, and money out takes units at this rate. | Read directly from the ledger | `reporting.fx_positions.Position.average_rate` |
| **Unrealized FX gain** | Today's value of the foreign money you hold minus what it cost: the exchange-rate gain or loss not yet locked in. | Read directly from the ledger | `reporting.fx_positions.Position.unrealized` |
| **Realized FX gain** | For foreign money that left in the period (spent or converted), what it fetched minus what it cost at the average rate. | Read directly from the ledger | `reporting.fx_positions.Position.realized` |
| **Spread paid** | What conversions in the period cost beyond the market rate of their day: the market value of what you sent minus the market value of what you received. Fees are separate. | Read directly from the ledger | `fx.spread_cost` |
| **Price part** | The part of a foreign holding's unrealized gain that comes from its price in its own currency, at today's rate. | Read directly from the ledger | `investments.report.foreign_gain_split` |
| **FX part** | The part of a foreign holding's unrealized gain that comes from the exchange rate. | Unrealized gain − Price part | `investments.report.foreign_gain_split` |

### From the plan — what-if

| Figure | Meaning | How it is calculated | Function |
|---|---|---|---|
| **Reserves** | Cash you set aside for emergencies and dated goals, less what linked payments already used. It stays in your accounts and in what you own. | Read directly from the plan | `reserves.CashReserveService.breakdown_at` |
| **Bills due** | Bills, subscriptions and loan payments dated today or earlier that nothing has paid yet. | Read directly from the plan | `planning.domain.WhatYouOwe.bills_due` |
| **Loans still to pay** | Every loan payment not paid yet, due or upcoming. | Read directly from the plan | `planning.domain.WhatYouOwe.loans_still_to_pay` |
| **Bills and subscriptions a month** | What your recurring bills and subscriptions come to in a month: a weekly one counts 52 times a year, a yearly one once, a one-off payment not at all. | Read directly from the plan | `planning.health.HealthService.bills_a_month` |
| **Loan payments a month** | What your loan payments come to in a month, counting only loans with payments still to make. | Read directly from the plan | `planning.health.HealthService.loans_a_month` |
| **Debts due now** | What you must pay today or earlier: your bills due. Zakat takes it off unless you turn that off. | Bills due | `planning.position.Position.bills_due` |
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
| **Cash available to assign** | Actual owned liquid cash left after reserves, funded spending and bills due outside those funds. Missing FX makes it unavailable; expected income never contributes. | Read directly from the plan | `planning.funding.CashFundingService.preview` |
| **Funded spending left** | This month's assigned category cash after owned spending and refunds, floored at zero. Unused funding does not carry automatically. | Read directly from the plan | `planning.funding.CashFundingService.preview` |
| **Outstanding reimbursement** | The eligible amount claimed for an owned expense that valid explicitly linked repayments or refunds have not covered. A claim is not cash before receipt. | Read directly from the plan | `reimbursements.ReimbursementService._claim_summary` |
| **What you owe** | Payments you are certain to make: bills already due, loans and what you owe a savings circle. | Bills due (other than loan payments) + Loans still to pay + Gam'eya still to pay | `planning.position.Position.what_you_owe` |
| **Net worth** | What you own after what you owe. | What you own − What you owe | `planning.position.Position.net_worth` |
| **Debt to net worth** | What you owe for each pound of net worth. None when net worth is zero or less. | What you owe ÷ Net worth | `planning.health.Ratio.percent` |
| **Debt to cash** | What you owe for each pound of cash you own: could your cash clear it today? | What you owe ÷ Cash you own | `planning.health.Ratio.percent` |
| **Loan payments to income** | The share of your income that goes to loan payments, counting only loans with payments still to make. | Loan payments a month ÷ Average monthly income | `planning.health.Ratio.percent` |
| **Fixed costs to income** | The share of your income already promised to bills, subscriptions and loan payments. | (Bills and subscriptions a month + Loan payments a month) ÷ Average monthly income | `planning.health.Ratio.percent` |
| **Free cash** | Cash you can spend without touching reserves or leaving a bill unpaid. Cash kept apart (brokerage, other currencies) is left out. | Cash you own − Kept apart − Reserves − Bills due | `planning.position.Position.free_cash` |
| **Holdings after sale (estimate)** | What your holdings, deposits included, might fetch if sold or cashed in today, after each class's sale factor. CDs before their earliest withdrawal count 0; early-redeemable CDs count their balance × the CD sale factor; matured CDs count their balance. | Σ Holdings value of each class × its sale factor | `planning.position.Position.holdings_after_sale` |
| **If you sold today (estimate)** | Free cash plus what your holdings might fetch. | Free cash + Holdings after sale (estimate) | `planning.position.Position.if_you_sold_today` |
| **Zakatable wealth** | What zakat is worked out on: what you hold, less the debts due now. | Cash you own + Deposits + Gam'eya paid in + Shares and funds + Gold held as savings + Gold you wear − Debts due now − Gam'eya instalments due now | `zakat.Assessment.zakatable_wealth` |
| **Zakat due** | An estimate by the common rule, for a scholar to confirm: the zakat rate of Zakatable wealth when it is at or above the Nisab, else nothing. | Zakatable wealth × Zakat rate | `zakat.Assessment.zakat_due` |
| **Still to pay** | What is left of Zakat due after what you paid this zakat year; never below zero. | Zakat due − Paid this zakat year | `zakat.Assessment.still_to_pay` |
| **Change in net worth** | How much net worth grew or shrank in the period. | Net worth at the end − Net worth the day before the start − Opening balances in the period | `planning.position.PositionService.change_in_net_worth` |
| **Carryover** | Unused plan from last month, added to this month when carryover is on. | Left in plan last month | `budgeting.domain.BudgetLine.opening_carryover` |
| **Planned** | What you plan to spend this month. The month's total also counts background estimates for untracked categories; one from a single month of spending is low confidence and shows a "!" that says why. | Base budget + Carryover | `budgeting.domain.BudgetLine.available` |
| **Left in plan** | What is left of the plan; the Overview and Budget show the same month figure, and a negative one reads "Over plan". One-off categories are left out of Spent. | Planned − Spent | `budgeting.domain.BudgetLine.remaining` |
| **Safe to spend** | Free cash after what is promised before your next income. An estimate. Budget until payday, Saving for goals, Emergency fund top-up and Rest of savings target count for every month until that income (only the days before it in the month it lands), so a long gap between pays is covered. | Free cash − Bills and loan payments before next income − Budget until payday − Saving for goals − Emergency fund top-up − Rest of savings target | `planning.forecast.CashForecaster._safe_to_spend` |
| **Budget until payday** | This month's left in plan less the scheduled bills it already covers, so a bill is never counted twice. | Left in plan − Bills inside the plan | `planning.domain.ForecastMonth.budget_spending` |

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
| Left in plan after bills | Budget until payday |
| Deposits and holdings after sale (estimate) | Holdings after sale (estimate) |
| Investments if sold (estimate) | Holdings after sale (estimate) |
| New money added this period | Money added |
| Cash added and withdrawn | Money added |
<!-- figures:end -->

## Category taxonomy (why the activity happened)

| Level | Meaning |
|---|---|
| **L1 Activity family** | Personal, Work, Investment. |
| **L2 Broad category** | The analysis bucket inside one family (Personal › Food & Groceries, Work › Salary, Investment › Dividends). |
| **L3 Detail** | Unused and empty; add only when a user chooses more detail. |

Categories are not split into income and expense trees: pick the activity that explains the event whatever its sign (a refund keeps the original category). A Counterparty may suggest a category; the user can change it. Categories are picked from a list, never created by typing. A used category is archived, not deleted: readable on old transactions, not selectable for new ones. Sibling names are unique; one name may sit under different families.

## Names and identifiers

| Term | Rule |
|---|---|
| **Name** | Human label on screens; account codes never show under it. Counterparty names are unique, other taxonomy names may repeat under different parents. |
| **Code** | Stable machine identifier for links, imports and technical search; not shown in ordinary UI. |
| **ID** | Internal database key; never shown. |
| **Ticker / symbol** | Public exchange symbol; not Lightning's code or ID. Optional ISIN also matches sources. |
| **Exchange** | Where a stock or ETF trades, stored as ISO 10383 MIC, shown by common name; no exchange means EGX; funds and gold have none. |
| **Price file** | One market's closing prices, published as a checked folder and refreshed after close; Settings › Price files picks them. Code: pack. |
| **Update prices** | Asks the sources for each held investment's latest close and missing month-end closes (source `ONLINE`); automatic only on the first open after a month ends; shared price files are the backup after two failed tries. |
| **Market key** | A price file's permanent name for an instrument: ISO 3166 country and ticker, `EG:FUND:<id>`, or a currency pair; stored on the matched asset. |
| **Unit** | What is counted for an asset. |
| **Transaction reference (ref)** | Fixed human ID, unchanged when the date is edited; a line adds `/n`. |
| **Date input** | ISO, day/month/year or day/month (current year); stored as ISO; ambiguous dates are day-first. |
| **Amount input** | A number (`1,250.50`, Arabic-Indic digits) or a sum with + - * / ^ and brackets, evaluated brackets, ^, * and /, then + and -; a bracket after a number multiplies. Unclear input is refused with the reason. |
| **Tag** | A #word in notes (letters, digits, - or _, at least one letter, case-insensitive); links to every transaction with it; same as the exact register search. |
| **Rule** | Settings › Rules: when counterparty, notes, amount, account or direction fit, set a category, add tags or split money out. The most specific wins; it applies before the counterparty's usual category; the past changes only on request. |
| **Privacy mode** | Blurs every money amount (not percentages, dates, names); hover shows it. The eye beside Search or "Hide amounts" in the command bar; remembered per profile. |

## Asset and account taxonomy (what vs where)

Asset class and exposure are separate. Account kinds describe the container: cash wallet, bank, deposit, brokerage (cash plus holdings), physical-asset location, other asset account. Code patterns: account `INSTITUTION-TYPE-CURRENCY` (`THNDR-BRK-EGP`); asset `CLASS:SYMBOL` (`STK:COMI`, `GLD:21K`).

## Transaction and posting types

`OPN` opening · `IN` inflow · `OUT` outflow · `TRF` internal transfer · `BUY` buy · `SEL` sell · `DIV` dividend · `VAL` system valuation · `ADJ` reconciliation adjustment · `CNV` currency conversion. Buy, sell and dividend are entered in the brokerage register.

## العربية — المسرد العربي

الأسماء العربية المصرية المعتمدة في التطبيق. الاسم الإنجليزي هو اسم الجدول أعلاه؛ المعنى والصيغة هناك.

| Term | Arabic |
|---|---|
| Ledger | السجل |
| Plan | الخطة |
| Report | التقرير |
| Account | الحساب |
| Financial asset | أصل مالي |
| Asset class | فئة الأصل |
| Exposure | التعرّض |
| Holding / position | حيازة / مركز |
| Balance | الرصيد |
| Transaction | معاملة |
| Main ledger | السجل الرئيسي |
| Transfer | تحويل |
| Investment trade | صفقة استثمار |
| Budget | ميزانيتك |
| Category | الفئة |
| Counterparty | الطرف الآخر |
| Held for | مملوك لـ |
| Name | الاسم |
| Code | الرمز |
| ID | المعرّف |
| Date | التاريخ |
| As of | كما في |
| Amount | المبلغ |
| Units | الوحدات |
| Notes | ملاحظات |
| Due date | تاريخ الاستحقاق |
| Sale factor | معامل البيع |
| Financial health | صحتك المالية |
| Home node / Home | الجهاز الرئيسي |
| Borrower | الجهاز المستعير |
| Checkout | إعارة الصلاحية |
| Checkpoint | نقطة تحقق |
| Lend | إعارة |
| Hand back | إعادة |
| Received | مستلَم |
| Accepted | مقبول |
| L1 — Activity family | المستوى الأول — عائلة النشاط |
| L2 — Broad category | المستوى الثاني — الفئة العامة |
| L3 — Detail | المستوى الثالث — التفصيل |
| Personal | شخصي |
| Work | عمل |
| Investment | استثمار |
| Opening | رصيد افتتاحي |
| Inflow | إيداع / وارد |
| Outflow | سحب / صادر |
| Investment buy / sell | شراء / بيع استثماري |
| Dividend | توزيعات |
| Valuation | تقييم |
| Reconciliation adjustment | تسوية مطابقة |
| Conversion | تحويل عملة |
| Physical item | مقتنى مادي |
| Net gold weight | الوزن الصافي للذهب |
| Fine-gold exposure | التعرّض للذهب الخالص |
| Acquisition cost | تكلفة الاقتناء |
| Manual item valuation | تقييم يدوي للمقتنى |
| Confirmed alias | اسم بديل مؤكد |
| Search suggestion | اقتراح بحث |
| Privacy mode | وضع الخصوصية |
| Amount input | إدخال المبلغ |
| Amount set aside | المبلغ المحجوز |
| CD terms | شروط شهادة الإيداع |
| Cash account | حساب النقد |
| Cash forecast | توقع النقد |
| Cash planning | تخطيط النقد |
| Change ownership | تغيير الملكية |
| Cost basis / average cost | أساس التكلفة / متوسط التكلفة |
| Date input | إدخال التاريخ |
| Earliest withdrawal date | أقرب تاريخ للسحب |
| Exchange | البورصة |
| Expense paid for you | مصروف دُفع نيابةً عنك |
| Fees | الرسوم |
| Financial health limit | حد الصحة المالية |
| ISIN | رقم ISIN |
|Karat-specific gold price | سعر الذهب حسب العيار |
| Last due date | آخر تاريخ استحقاق |
| Ledger-line reference | مرجع القيد |
| Linked (import row) | مرتبط (صف مستورد) |
| Market key | مفتاح السوق |
| Observed-month average | متوسط الأشهر المسجلة |
| Opening adjustment | تسوية افتتاحية |
| Owner ID | معرّف المالك |
| Payment status | حالة الدفع |
| Payments left / Number of payments | الدفعات المتبقية / عدد الدفعات |
| Price file | ملف الأسعار |
| Realized / unrealized return | عائد محقق / غير محقق |
| Recurring item | بند متكرر |
| Reevaluation ledger | سجل إعادة التقييم |
| Revaluation | إعادة تقييم |
| Rule | قاعدة |
| Saving needed | المطلوب ادخاره |
| System-generated posting | قيد ينشئه النظام |
| Tag | وسم |
| Target amount | المبلغ المستهدف |
| Ticker / symbol | رمز التداول |
| Transaction reference (ref) | مرجع المعاملة |
| Type | النوع |
| Update prices | تحديث الأسعار |
| Value | القيمة |
| Void / delete | إلغاء / حذف |
| XIRR | العائد السنوي الداخلي |
| In your accounts | في حساباتك |
| Held for others | أموال لغيرك |
| What you own | اللي تملكه |
| Bank and wallet cash | نقدية البنك والمحفظة |
| Brokerage cash | نقدية الاستثمار |
| Cash you own | النقدية اللي تملكها |
| Deposits | الودائع والشهادات |
| Gam'eya paid in | جمعية مدفوعة |
| Gam'eya still to pay | جمعية لسه عليك |
| Holdings value | قيمة الاستثمارات |
| Other you own | أصول تانية تملكها |
| Reserves | المبالغ المحجوزة |
| Bills due | فواتير مستحقة |
| Loans still to pay | قروض لسه عليك |
| What you owe | اللي عليك |
| Net worth | صافي ثروتك |
| Bills and subscriptions a month | الفواتير والاشتراكات شهريًا |
| Loan payments a month | أقساط القروض شهريًا |
| Debt to net worth | الديون مقارنة بصافي ثروتك |
| Debt to cash | الديون مقارنة بالنقدية |
| Loan payments to income | أقساط القروض من دخلك |
| Fixed costs to income | المصاريف الثابتة من دخلك |
| Free cash | النقدية المتاحة |
| Portfolio value | قيمة المحفظة |
| Holdings after sale (estimate) | قيمة الاستثمارات بعد البيع (تقديري) |
| If you sold today (estimate) | لو بعت النهارده (تقديري) |
| Zakat | الزكاة |
| Zakat day | يوم الزكاة |
| Zakatable wealth | المال اللي بتتحسب عليه الزكاة |
| Nisab | النصاب |
| Zakat rate | نسبة الزكاة |
| Zakat due | الزكاة المستحقة |
| Paid this zakat year | اللي دفعته السنة دي |
| Shares and funds | الأسهم والصناديق |
| Gold held as savings | الدهب المحتفظ بيه كمدخرات |
| Gold you wear | الدهب اللي بتلبسه |
| Debts due now | ديون مستحقة دلوقتي |
| Money in | فلوس داخلة |
| Money out | فلوس خارجة |
| Net flow | صافي التدفق |
| Savings rate | نسبة الادخار |
| Opening balances in the period | الأرصدة الافتتاحية خلال الفترة |
| Change in what you own | التغير في اللي تملكه |
| Change in net worth | التغير في صافي ثروتك |
| Per month | شهريًا |
| Usual month | الشهر المعتاد |
| Usual range | النطاق المعتاد |
| Investing rate | نسبة الاستثمار |
| Average monthly income | متوسط الدخل الشهري |
| Average monthly spending | متوسط المصروفات الشهرية |
| Base budget | الميزانية الأساسية |
| Carryover / Budget carryover | المبلغ المرحّل |
| Planned | المخطط |
| Spent | المنفق |
| Left in plan | المتبقي في الخطة |
| Plan leaves to save | المتبقي للادخار من الخطة |
| Planned savings rate | نسبة الادخار المخططة |
| Savings target | هدف الادخار |
| Emergency fund top-up | زيادة صندوق الطوارئ |
| Most you can plan | أقصى مبلغ تقدر تخطط له |
| Cost | التكلفة |
| Unrealized gain | ربح غير محقق |
| Price change on what you hold | تغير قيمة المقتنيات |
| Gain from sales | أرباح البيع |
| Dividends and interest | توزيعات وفوائد |
| Net gain or loss | صافي الربح أو الخسارة |
| Money added | فلوس مضافة |
| Typical move | الحركة المعتادة |
| Fall from its high | الانخفاض من أعلى قيمة |
| Average cost | متوسط التكلفة |
| Growth | النمو |
| Average rate | متوسط السعر |
| Unrealized FX gain | ربح فروق العملة غير المحقق |
| Realized FX gain | ربح فروق العملة المحقق |
| Spread paid | فرق السعر المدفوع |
| Price part | جزء السعر |
| FX part | جزء العملة |
| Safe to spend | المتاح الآمن للصرف |
| Bills inside the plan | الفواتير ضمن الخطة |
| Budget until payday | الميزانية لحد الراتب |
| Bills and loan payments before next income | الفواتير والأقساط قبل الدخل القادم |
| Saving for goals | الادخار للأهداف |
| Rest of savings target | باقي هدف الادخار |
| Activity | النشاط |
| Loan | قرض |
| Reserve | مبلغ محجوز |
| Opening balance | رصيد افتتاحي |
| Unit | وحدة |
| Paid | مدفوع |
| Skipped | متخطّى |
| Due | مستحق |
| Upcoming | قادم |
| From | من |
