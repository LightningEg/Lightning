"""One name, one meaning, one formula and one function for every figure Lightning reports.

Lightning has three layers:

- **Ledger** — real money. Posted transactions: where money actually came from and went.
- **Plan** — what-if. Budgets, reserves, scheduled bills and loans, sale factors and the forecast.
  Nothing in it moves money; it sits on top of the ledger to help you plan.
- **Report** — reads the other two and presents them. It stores nothing of its own.

Every figure below is shown by the report layer. Its ``layer`` says where its inputs come from
(the ledger, the plan, or both), and ``function`` names the one piece of code that computes it.
Screens read labels and formulas from here, so a figure is never called one thing on one tab and
something else on another, and a derived figure is a formula of other figures, never computed a
second way. docs/GLOSSARY.md is generated from this table; tests keep them in step and check that
every ``function`` exists.
"""
from __future__ import annotations

from dataclasses import dataclass


LEDGER, PLAN, BOTH = "Ledger", "Plan", "Ledger + Plan"
LAYERS = {
    LEDGER: "Real money: posted transactions and the balances and prices they give.",
    PLAN: "What-if: budgets, reserves, scheduled bills and loans, sale factors and forecasts. Moves no money.",
    BOTH: "Real money adjusted by a plan, for example cash after what is set aside.",
}


@dataclass(frozen=True)
class Figure:
    key: str
    label: str
    meaning: str
    formula: str = ""        # empty for a base figure read directly from its layer
    layer: str = LEDGER      # where its inputs come from
    function: str = ""       # dotted path of the code that computes it

    @property
    def equation(self) -> str:
        return f"{self.label} = {self.formula}" if self.formula else ""


_TABLE = [
    ("cash_available_to_assign", "Cash available to assign",
     "Actual owned liquid cash left after reserves, funded spending and bills due outside those funds. Missing FX makes it unavailable; expected income never contributes.",
     ""),
    ("funded_spending_left", "Funded spending left",
     "This month's assigned category cash after owned spending and refunds, floored at zero. Unused funding does not carry automatically.",
     ""),
    ("reimbursement_outstanding", "Outstanding reimbursement",
     "The eligible amount claimed for an owned expense that valid explicitly linked repayments or refunds have not covered. A claim is not cash before receipt.",
     ""),
    # ------------------------------------------------------------ position (a date)
    ("in_your_accounts", "In your accounts", "Everything in your accounts, including what you hold for other people.",
     "What you own + Held for others"),
    ("held_for_others", "Held for others", "Money and units in your accounts that belong to other people."),
    ("what_you_own", "What you own", "The value of everything in your accounts that is yours.",
     "Cash you own + Holdings value + Other you own"),
    ("bank_and_wallet_cash", "Bank and wallet cash", "Your cash in bank accounts and wallets."),
    ("brokerage_cash", "Brokerage cash", "Your uninvested cash inside brokerage accounts."),
    ("cash_you_own", "Cash you own", "Your cash in banks, wallets and brokerage accounts.",
     "Bank and wallet cash + Brokerage cash"),
    ("deposits", "Deposits", "Your certificates and time deposits, at their balance. They are part of Holdings value."),
    ("gameya_paid_in", "Gam'eya paid in", "What you have paid into your savings circles and not yet taken out: a "
     "circle's balance while it owes you. It is part of Holdings value, a circle cannot be sold early (100%)."),
    ("holdings_value", "Holdings value", "Everything you own that is not cash, at its latest value: certificates and "
     "deposits, Gam'eya paid in, stocks, funds, gold and other assets. Assets that are not cash sit under one roof "
     "(owner decision 2026-10-04)."),
    ("other_you_own", "Other you own", "Anything you own that is neither cash nor a holding.",
     "What you own − Cash you own − Holdings value"),
    ("reserves", "Reserves", "Cash you set aside for emergencies and dated goals, less what linked payments "
     "already used. It stays in your accounts and in what you own."),
    ("bills_due", "Bills due", "Bills, subscriptions and loan payments dated today or earlier that nothing has paid yet."),
    ("loans_still_to_pay", "Loans still to pay", "Every loan payment not paid yet, due or upcoming."),
    ("gameya_still_to_pay", "Gam'eya still to pay", "What you owe a savings circle you took the pot from early: "
     "its balance while it is below zero. Net worth does not change when you take the pot."),
    ("what_you_owe", "What you owe", "Payments you are certain to make: bills already due, loans and what you owe "
     "a savings circle.",
     "Bills due (other than loan payments) + Loans still to pay + Gam'eya still to pay"),
    ("net_worth", "Net worth", "What you own after what you owe.", "What you own − What you owe"),
    ("bills_a_month", "Bills and subscriptions a month", "What your recurring bills and subscriptions come to in a "
     "month: a weekly one counts 52 times a year, a yearly one once, a one-off payment not at all."),
    ("loan_payments_a_month", "Loan payments a month", "What your loan payments come to in a month, counting only "
     "loans with payments still to make."),
    ("debt_to_net_worth", "Debt to net worth", "What you owe for each pound of net worth. None when net worth is zero or less.",
     "What you owe ÷ Net worth"),
    ("debt_to_cash", "Debt to cash", "What you owe for each pound of cash you own: could your cash clear it today?",
     "What you owe ÷ Cash you own"),
    ("loan_payments_to_income", "Loan payments to income",
     "The share of your income that goes to loan payments, counting only loans with payments still to make.",
     "Loan payments a month ÷ Average monthly income"),
    ("fixed_costs_to_income", "Fixed costs to income",
     "The share of your income already promised to bills, subscriptions and loan payments.",
     "(Bills and subscriptions a month + Loan payments a month) ÷ Average monthly income"),
    ("kept_apart", "Kept apart", "Cash you own that is not ready to spend: cash in a brokerage, cash in another "
     "currency, or an account you set apart. It stays in what you own and in If you sold today."),
    ("free_cash", "Free cash", "Cash you can spend without touching reserves or leaving a bill unpaid. Cash kept "
     "apart (brokerage, other currencies) is left out.",
     "Cash you own − Kept apart − Reserves − Bills due"),
    ("portfolio_value", "Portfolio value", "Holdings value under the name the Investments tab uses: everything "
     "you own that is not cash. Cash waiting in a brokerage account counts in Cash you own (owner decisions "
     "2026-10-04).", "Holdings value"),
    ("holdings_after_sale", "Holdings after sale (estimate)",
     "What your holdings, deposits included, might fetch if sold or cashed in today, after each class's sale "
     "factor. CDs before their earliest withdrawal count 0; early-redeemable CDs count their balance × the CD "
     "sale factor; matured CDs count their balance.",
     "Σ Holdings value of each class × its sale factor"),
    ("if_you_sold_today", "If you sold today (estimate)",
     "Free cash plus what your holdings might fetch.",
     "Free cash + Holdings after sale (estimate)"),
    # ------------------------------------------------------------ zakat (an estimate by the common rule)
    ("shares_and_funds", "Shares and funds", "Your stocks and funds at their latest value, counted in full for zakat."),
    ("gold_held_as_savings", "Gold held as savings", "Your gold pieces and gold by the gram that you keep as savings, at "
     "the gold price. Pieces marked as worn are left out."),
    ("gold_you_wear", "Gold you wear", "Your gold pieces marked as worn. Zakat counts them only if you turn that on."),
    ("debts_due_now", "Debts due now", "What you must pay today or earlier: your bills due. Zakat takes it off unless "
     "you turn that off.", "Bills due"),
    ("gameya_due_now", "Gam'eya instalments due now", "Instalments dated today or earlier and not yet recorded, on "
     "a savings circle you took the pot from early. Zakat takes them off with the debts due now."),
    ("zakatable_wealth", "Zakatable wealth", "What zakat is worked out on: what you hold, less the debts due now.",
     "Cash you own + Deposits + Gam'eya paid in + Shares and funds + Gold held as savings + Gold you wear "
     "− Debts due now − Gam'eya instalments due now"),
    ("nisab", "Nisab", "The least wealth zakat applies to: 85 g of 24K gold at the gold price of the day, or the "
     "amount you typed when there is no gold price."),
    ("zakat_rate", "Zakat rate", "The share of zakatable wealth that is due: 2.5% by the common rule."),
    ("zakat_due", "Zakat due", "An estimate by the common rule, for a scholar to confirm: the zakat rate of Zakatable "
     "wealth when it is at or above the Nisab, else nothing.", "Zakatable wealth × Zakat rate"),
    ("zakat_paid", "Paid this zakat year", "What you spent in the Zakat category since your last zakat day, up to the "
     "next."),
    ("zakat_still_to_pay", "Still to pay", "What is left of Zakat due after what you paid this zakat year; never below "
     "zero.", "Zakat due − Paid this zakat year"),
    # ------------------------------------------------------------ activity (a period)
    ("money_in", "Money in", "Your posted income in the period. Transfers, trades and money held for others are left out."),
    ("money_out", "Money out", "Your posted spending in the period, after refunds. Transfers, trades and money held for others are left out."),
    ("net_flow", "Net flow", "What was left of money in after money out.", "Money in − Money out"),
    ("savings_rate", "Savings rate", "The share of money in that you kept. When money out is more than twice money "
     "in (below −100%, such as a month whose pay came early), the Overview and Financial health say the gap in "
     "words instead.", "Net flow ÷ Money in"),
    ("opening_balances_in_period", "Opening balances in the period", "Money and assets you recorded as already yours (opening balances and existing holdings) during the period. They were yours before, so they are not a change."),
    ("change_in_what_you_own", "Change in what you own", "How much what you own grew or shrank in the period.",
     "What you own at the end − What you own the day before the start − Opening balances in the period"),
    ("change_in_net_worth", "Change in net worth", "How much net worth grew or shrank in the period.",
     "Net worth at the end − Net worth the day before the start − Opening balances in the period"),
    ("per_month", "Per month", "A period's money out divided by the calendar months it covers, so a year to date "
     "compares with a single month."),
    ("usual_month", "Usual month", "The average money out of the last six earlier months, using matching calendar days for a partial period."),
    ("usual_savings_rate", "Usual savings rate", "The average savings rate of the last six earlier whole months that had money "
     "in; a month whose rate says nothing is left out."),
    ("usual_range", "Usual range", "The lowest, middle and highest money out of the twelve earlier months, using matching calendar days "
     "for a partial period. It needs three of them."),
    ("investing_rate", "Investing rate", "The share of what you kept (net flow) that you moved into investments. "
     "Money from earlier savings does not count, so it is never more than 100%.", "Money added ÷ Net flow"),
    ("average_monthly_income", "Average monthly income",
     "Income in your chosen income categories, averaged over the last 3 or 6 completed months that had any "
     "(Settings › Budget). Until a completed month has income, the income set up in Recurring stands in. "
     "The budget, reserves and the cash forecast all use it."),
    ("average_monthly_spending", "Average monthly spending",
     "Money out in your budget categories, leaving out investments and one-off categories, averaged over the same "
     "3 or 6 completed months as Average monthly income. The emergency fund can be counted in it (Settings › Budget)."),
    # ------------------------------------------------------------ budget (a month)
    ("base_budget", "Base budget", "The amount the budget rule gives: fixed, a share of income or an average."),
    ("carryover", "Carryover", "Unused plan from last month, added to this month when carryover is on.",
     "Left in plan last month"),
    ("planned", "Planned", "What you plan to spend this month. The month's total also counts background "
     "estimates for untracked categories; one from a single month of spending is low confidence and shows a "
     "\"!\" that says why.", "Base budget + Carryover"),
    ("spent", "Spent", "Money out in the category this month."),
    ("left_in_plan", "Left in plan", "What is left of the plan; the Overview and Budget show the same month "
     "figure, and a negative one reads \"Over plan\". One-off categories are left out of Spent.", "Planned − Spent"),
    ("plan_leaves_to_save", "Plan leaves to save", "What this month's plan leaves of average monthly income.",
     "Average monthly income − Planned"),
    ("planned_savings_rate", "Planned savings rate", "The share of average monthly income this month's plan "
     "leaves unspent. Financial health compares it with your Savings rate limit; the budget and Needs you warn "
     "when it falls short.", "Plan leaves to save ÷ Average monthly income"),
    ("savings_target", "Savings target", "What your Savings rate limit (Financial health) asks you to keep each "
     "month: Average monthly income times that limit."),
    ("emergency_top_up", "Emergency fund top-up", "What the emergency fund lacks to reach six months, spread over "
     "two years (owner request 2026-10-05). Nothing once the fund is full."),
    ("saving_needed", "Saving needed", "What this month's plan must leave: the Savings target, or Saving for goals plus "
     "Emergency fund top-up when they need more."),
    ("spending_room", "Most you can plan", "The largest plan that still leaves what you need to save. It replaced the "
     "budget's separate spending ceiling (2026-10-05).", "Average monthly income − Saving needed"),
    # ------------------------------------------------------------ investments (a period)
    ("cost", "Cost", "What you paid for the units you still hold."),
    ("unrealized_gain", "Unrealized gain", "Gain or loss on units you still hold.", "Holdings value − Cost"),
    ("change_in_unrealized_gain", "Price change on what you hold", "How unrealized gain moved in the period.",
     "Unrealized gain at the end − Unrealized gain at the start"),
    ("realized_gain", "Gain from sales", "Sale proceeds less the cost of the units sold."),
    ("dividends_and_interest", "Dividends and interest", "Distributions and interest received."),
    ("result", "Net gain or loss", "What your investments earned or lost in the period: sales, price changes and payouts.",
     "Gain from sales + Price change on what you hold + Dividends and interest"),
    ("new_money_in", "Money added", "Cash moved into investment accounts from outside, less cash taken out."),
    ("typical_move", "Typical move", "How much a holding's month-end price usually moves in a month: the spread "
     "(standard deviation) of its monthly price changes, once there are three."),
    ("fall_from_high", "Fall from its high", "How far a holding's month-end price sits below the highest month-end "
     "price before it, in percent."),
    ("average_cost", "Average cost", "What you paid for each unit you still hold, fees included.", "Cost ÷ Units"),
    ("period_growth", "Growth", "Net gain or loss as a share of what the portfolio started the period with, plus money added.",
     "Net gain or loss ÷ (Portfolio value at the start + Money added)"),
    # ------------------------------------------------------------ foreign money (a period)
    ("average_rate", "Average rate", "What each unit of a foreign currency you still hold cost you, in the profile "
     "currency: conversions count at the rate you got, money in at the day's rate, and money out takes units at this rate."),
    ("unrealized_fx_gain", "Unrealized FX gain", "Today's value of the foreign money you hold minus what it cost: the "
     "exchange-rate gain or loss not yet locked in."),
    ("realized_fx_gain", "Realized FX gain", "For foreign money that left in the period (spent or converted), what it "
     "fetched minus what it cost at the average rate."),
    ("spread_paid", "Spread paid", "What conversions in the period cost beyond the market rate of their day: the market "
     "value of what you sent minus the market value of what you received. Fees are separate."),
    ("price_part", "Price part", "The part of a foreign holding's unrealized gain that comes from its price in its own "
     "currency, at today's rate."),
    ("fx_part", "FX part", "The part of a foreign holding's unrealized gain that comes from the exchange rate.",
     "Unrealized gain − Price part"),
    # ------------------------------------------------------------ cash planning
    ("safe_to_spend", "Safe to spend", "Free cash after what is promised before your next income. An estimate. Budget until payday, Saving for goals, Emergency fund top-up and Rest of savings target count for every month until that income (only the days before it in the month it lands), so a long gap between pays is covered.",
     "Free cash − Due before payday − Budget until payday − Saving for goals − Emergency fund top-up − Rest of savings target"),
    ("bills_inside_the_plan", "Bills inside the plan",
     "This month's scheduled bills, due or upcoming, in a category that has a budget. They are part of that budget."),
    ("left_in_plan_after_bills", "Budget until payday",
     "This month's left in plan less the scheduled bills it already covers, so a bill is never counted twice.",
     "Left in plan − Bills inside the plan"),
    ("everyday_spending", "Everyday spending",
     "This month's Spent less the plan's bills and loan payments already paid (or paid to that bill's payee in its "
     "category): what Budget's day rate is about. Budget compares it with the plan's straight-line pace and with "
     "last month by the same day."),
    ("payments_before_next_income", "Due before payday",
     "Scheduled bills, subscriptions and loan payments that are not due yet, up to your next income."),
    ("saving_for_goals", "Saving for goals", "What dated reserve goals still need this month, spread over the months left."),
    ("savings_target_rest", "Rest of savings target", "What the Savings target asks a month beyond Saving for goals and "
     "Emergency fund top-up (never below zero), so Safe to spend never counts what you mean to save (owner "
     "decision 2026-10-05).", "Savings target − Saving for goals − Emergency fund top-up"),
]

P, WYO, CF, BL = ("lightning.planning.position.Position", "lightning.planning.domain.WhatYouOwe",
                  "lightning.reporting.service.CashFlow", "lightning.budgeting.domain.BudgetLine")
INV, FC = "lightning.investments.report", "lightning.planning.forecast.CashForecaster"
_SOURCES = {
    "cash_available_to_assign": (BOTH, "lightning.planning.funding.CashFundingService.preview"),
    "funded_spending_left": (BOTH, "lightning.planning.funding.CashFundingService.preview"),
    "reimbursement_outstanding": (BOTH, "lightning.reimbursements.ReimbursementService._claim_summary"),
    "in_your_accounts": (LEDGER, f"{P}.in_your_accounts"),
    "held_for_others": (LEDGER, "lightning.reporting.service.ReportingService.money_from_others_total"),
    "what_you_own": (LEDGER, "lightning.reporting.service.ReportingService.net_worth"),
    "bank_and_wallet_cash": (LEDGER, f"{P}.bank_and_wallet_cash"),
    "brokerage_cash": (LEDGER, "lightning.reporting.service.ReportingService.owned_brokerage_cash"),
    "cash_you_own": (LEDGER, f"{P}.cash_you_own"),
    "deposits": (LEDGER, f"{P}.deposits"),
    "gameya_paid_in": (LEDGER, f"{P}.gameya_paid_in"),
    "holdings_value": (LEDGER, f"{P}.holdings_value"),
    "other_you_own": (LEDGER, f"{P}.other_you_own"),
    "reserves": (PLAN, "lightning.reserves.CashReserveService.breakdown_at"),
    "bills_due": (PLAN, f"{WYO}.bills_due"),
    "loans_still_to_pay": (PLAN, f"{WYO}.loans_still_to_pay"),
    "gameya_still_to_pay": (LEDGER, f"{P}.gameya_still_to_pay"),
    "what_you_owe": (BOTH, f"{P}.what_you_owe"),
    "net_worth": (BOTH, f"{P}.net_worth"),
    "bills_a_month": (PLAN, "lightning.planning.health.HealthService.bills_a_month"),
    "loan_payments_a_month": (PLAN, "lightning.planning.health.HealthService.loans_a_month"),
    "debt_to_net_worth": (BOTH, "lightning.planning.health.Ratio.percent"),
    "debt_to_cash": (BOTH, "lightning.planning.health.Ratio.percent"),
    "loan_payments_to_income": (BOTH, "lightning.planning.health.Ratio.percent"),
    "fixed_costs_to_income": (BOTH, "lightning.planning.health.Ratio.percent"),
    "kept_apart": (LEDGER, "lightning.reporting.service.ReportingService.owned_cash_kept_apart"),
    "free_cash": (BOTH, f"{P}.free_cash"),
    "portfolio_value": (LEDGER, f"{P}.portfolio_value"),
    "holdings_after_sale": (BOTH, f"{P}.holdings_after_sale"),
    "if_you_sold_today": (BOTH, f"{P}.if_you_sold_today"),
    "shares_and_funds": (LEDGER, "lightning.zakat.ZakatService.assess"),
    "gold_held_as_savings": (LEDGER, "lightning.zakat.ZakatService.assess"),
    "gold_you_wear": (LEDGER, "lightning.zakat.ZakatService.assess"),
    "debts_due_now": (PLAN, f"{P}.bills_due"),
    "gameya_due_now": (LEDGER, "lightning.zakat.ZakatService.gameya_due_now"),
    "zakatable_wealth": (BOTH, "lightning.zakat.Assessment.zakatable_wealth"),
    "nisab": (LEDGER, "lightning.zakat.ZakatService.nisab"),
    "zakat_rate": (LEDGER, "lightning.zakat.ZAKAT_RATE"),
    "zakat_due": (BOTH, "lightning.zakat.Assessment.zakat_due"),
    "zakat_paid": (LEDGER, "lightning.zakat.ZakatService.paid_between"),
    "zakat_still_to_pay": (BOTH, "lightning.zakat.Assessment.still_to_pay"),
    "money_in": (LEDGER, f"{CF}.inflows"),
    "money_out": (LEDGER, f"{CF}.outflows"),
    "net_flow": (LEDGER, f"{CF}.net"),
    "savings_rate": (LEDGER, f"{CF}.savings_rate"),
    "opening_balances_in_period": (LEDGER, "lightning.reporting.service.ReportingService.opening_balances_between"),
    "change_in_what_you_own": (LEDGER, "lightning.planning.position.PositionService.change_in_what_you_own"),
    "change_in_net_worth": (BOTH, "lightning.planning.position.PositionService.change_in_net_worth"),
    "per_month": (LEDGER, "lightning.reporting.spending.spending_profile"),
    "usual_month": (LEDGER, "lightning.reporting.spending._against_history"),
    "usual_range": (LEDGER, "lightning.reporting.spending._against_history"),
    "usual_savings_rate": (LEDGER, "lightning.reporting.service.ReportingService.usual_savings_rate"),
    "typical_move": (LEDGER, "lightning.investments.journey.holding_history"),
    "fall_from_high": (LEDGER, "lightning.investments.journey.holding_history"),
    "investing_rate": (LEDGER, f"{INV}.investing_rate"),
    "average_monthly_income": (LEDGER, "lightning.budgeting.service.BudgetService.income_average"),
    "average_monthly_spending": (LEDGER, "lightning.budgeting.service.BudgetService.spending_average"),
    "base_budget": (PLAN, f"{BL}.budget"),
    "carryover": (BOTH, f"{BL}.opening_carryover"),
    "planned": (BOTH, f"{BL}.available"),
    "spent": (LEDGER, f"{BL}.actual"),
    "left_in_plan": (BOTH, f"{BL}.remaining"),
    "plan_leaves_to_save": (PLAN, "lightning.planning.health.PlanCheck.plan_saves"),
    "planned_savings_rate": (PLAN, "lightning.planning.health.PlanCheck.planned_savings_rate"),
    "savings_target": (PLAN, "lightning.planning.health.PlanCheck.savings_target"),
    "spending_room": (PLAN, "lightning.planning.health.PlanCheck.spending_room"),
    "saving_needed": (PLAN, "lightning.planning.health.PlanCheck.to_save"),
    "emergency_top_up": (PLAN, "lightning.budgeting.domain.EmergencyFund.top_up"),
    "cost": (LEDGER, f"{INV}.build_investment_report"),
    "unrealized_gain": (LEDGER, f"{INV}.build_investment_report"),
    "change_in_unrealized_gain": (LEDGER, f"{INV}.investment_period"),
    "realized_gain": (LEDGER, f"{INV}.build_investment_report"),
    "dividends_and_interest": (LEDGER, f"{INV}.build_investment_report"),
    "result": (LEDGER, f"{INV}.investment_period"),
    "new_money_in": (LEDGER, f"{INV}.build_investment_report"),
    "average_cost": (LEDGER, "lightning.investments.domain.Position.average_cost"),
    "period_growth": (LEDGER, f"{INV}.period_growth"),
    "average_rate": (LEDGER, "lightning.reporting.fx_positions.Position.average_rate"),
    "unrealized_fx_gain": (LEDGER, "lightning.reporting.fx_positions.Position.unrealized"),
    "realized_fx_gain": (LEDGER, "lightning.reporting.fx_positions.Position.realized"),
    "spread_paid": (LEDGER, "lightning.fx.spread_cost"),
    "price_part": (LEDGER, f"{INV}.foreign_gain_split"),
    "fx_part": (LEDGER, f"{INV}.foreign_gain_split"),
    "safe_to_spend": (BOTH, f"{FC}._safe_to_spend"),
    "bills_inside_the_plan": (PLAN, f"{FC}.forecast"),
    "left_in_plan_after_bills": (BOTH, "lightning.planning.domain.ForecastMonth.budget_spending"),
    "everyday_spending": (BOTH, "lightning.planning.domain.EverydayBudget.everyday_spent"),
    "payments_before_next_income": (PLAN, f"{FC}._safe_to_spend"),
    "saving_for_goals": (PLAN, f"{FC}._goal_need"),
    "savings_target_rest": (PLAN, f"{FC}.forecast"),
}
FIGURES: dict[str, Figure] = {
    row[0]: Figure(*row, layer=_SOURCES[row[0]][0], function=_SOURCES[row[0]][1]) for row in _TABLE}

# Names that used to appear on screens, each mapped to the figure that replaced it.
RETIRED_NAMES = {
    "Bills and loan payments before next income": "payments_before_next_income",
    "All accounts": "in_your_accounts", "Gross balances": "in_your_accounts",
    "Money from others": "held_for_others", "Cash held for others": "held_for_others",
    "Owned value": "what_you_own", "Owned net worth": "what_you_own", "What I own": "what_you_own",
    "Liquid cash": "cash_you_own", "Owned liquid cash": "cash_you_own",
    "Investment cash": "brokerage_cash",
    "Investments and deposits": "deposits", "Investment holdings": "holdings_value",
    "Current owned value": "holdings_value", "Other owned assets": "other_you_own",
    "Assigned reserves": "reserves", "Assigned to reserves": "reserves", "Cash reserved": "reserves",
    "Estimated liquid investments": "holdings_after_sale", "Estimated cash after sale": "holdings_after_sale",
    "Estimated available value": "if_you_sold_today",
    "Yours": "what_you_own",
    "Total spending": "money_out", "Net income less spending": "net_flow", "Cashflow": "net_flow",
    "Average monthly salary": "average_monthly_income", "Budgeted": "planned", "Current budget": "planned",
    "Invested capital": "cost", "What you paid in total": "cost",
    "Unrealized gain/loss": "unrealized_gain", "Change in unrealized value": "change_in_unrealized_gain",
    "Realized gain or loss": "realized_gain", "Distributions": "dividends_and_interest",
    "Investment result": "result", "Period result": "result", "Period gain/loss": "result", "Result": "result",
    "Realized gain": "realized_gain", "Change in unrealized gain": "change_in_unrealized_gain",
    "New money in": "new_money_in", "Left in plan after bills": "left_in_plan_after_bills",
    "Deposits and holdings after sale (estimate)": "holdings_after_sale",
    "Investments if sold (estimate)": "holdings_after_sale",
    "New money added this period": "new_money_in", "Cash added and withdrawn": "new_money_in",
}


def label(key: str) -> str:
    return FIGURES[key].label


def equation(key: str) -> str:
    return FIGURES[key].equation


# Fields on the forms that record values, one name each (layer = where the value is recorded).
FIELDS = [
    ("Date", LEDGER, "The day money moved.", "Date paid, Date received"),
    ("As of", LEDGER, "The day a balance, holding, price or value is true.", "Price date, Statement date"),
    ("Amount", BOTH, "Money moved, in the account's currency. A trade's amount includes fees unless "
     "*Fees are extra* is ticked; a scheduled item's amount is each payment.",
     "Total paid, Total paid / received, Each payment, Total amount received"),
    ("Balance", LEDGER, "An account balance on the As of date.", "Statement closing balance"),
    ("Value", LEDGER, "What a holding or item is worth on the As of date.", "Total item value, Current value"),
    ("Cost", LEDGER, "What you paid in total for units you already hold, fees included.",
     "What you paid in total, Invested capital"),
    ("Units", LEDGER, "Shares, fund units, grams or pieces.", "Quantity, Pieces, Units you hold"),
    ("Account", BOTH, "Where the money moves or the holding sits.", "Held in, Received into, Paid from, Paid into"),
    ("Cash account", LEDGER, "The account that pays or receives the cash for a trade in another account.",
     "Paid from / received into, Money goes to"),
    ("Counterparty", BOTH, "Who you paid or who paid you.", "Paid to, From, Search counterparty"),
    ("Held for", LEDGER, "The person the money or units belong to, if not you.",
     "Whom, Owned by, Owner, Money held for someone else"),
    ("Category", BOTH, "What the money was for.", "Search category"),
    ("Type", BOTH, "The kind of record.", "Kind, Action"),
    ("Name", BOTH, "The record's name.", "Item name"),
    ("Notes", BOTH, "Free text.", "Details"),
    ("Fees", LEDGER, "Fees inside the amount (tick *Fees are extra* when they are not).",
     "Fees included in total, Fees are excluded from the total"),
    ("Due date", PLAN, "When a scheduled payment is due; when adding, the next one; when editing, the first.",
     "Next date, Next payment date"),
    ("Last due date", PLAN, "The last scheduled payment, when a recurring item ends.", "Last date"),
    ("Payments left / Number of payments", PLAN, "How many loan payments; counted from the first due date.", ""),
    ("Amount set aside", PLAN, "Cash assigned to a reserve. It stays in your account.", "Cash reserved, Cash assigned"),
    ("Target amount", PLAN, "What a reserve is saving towards.", ""),
    ("Sale factor", PLAN, "The share of a class's value you expect if you sold today (95% when not set).",
     "Liquidation factor"),
]

MODULES = {
    LEDGER: ("`lightning.accounts`, `lightning.transactions`, `lightning.assets`, investment trades in "
             "`lightning.investments`", "Yes. Every posted transaction."),
    PLAN: ("`lightning.budgeting`, `lightning.reserves`, `lightning.planning` (items, payments, forecast), "
           "sale factors", "No. Recording a payment from the plan posts an ordinary ledger transaction."),
    "Report": ("`lightning.reporting`, `lightning.planning.position`, `lightning.investments.report`, "
               "`lightning.integrity`, every screen in `lightning.ui`", "No. It only reads the other two."),
}


def glossary_markdown() -> str:
    """The Glossary's figures section, generated from this module (see tests/test_figures.py)."""
    short = lambda path: path.removeprefix("lightning.")
    out = ["## Three layers: ledger, plan, report", "",
           "Lightning keeps real money and plans apart, and reports on both:", "",
           "| Layer | What it holds | Where in the code | Moves money? |", "|---|---|---|---|",
           f"| **Ledger** (real money) | {LAYERS[LEDGER]} | {MODULES[LEDGER][0]} | {MODULES[LEDGER][1]} |",
           f"| **Plan** (what-if) | {LAYERS[PLAN]} | {MODULES[PLAN][0]} | {MODULES[PLAN][1]} |",
           f"| **Report** | Reads the ledger and the plan and presents them; stores nothing. | {MODULES['Report'][0]} "
           f"| {MODULES['Report'][1]} |", "",
           "The plan reads the ledger; the report reads both. A plan figure never changes a ledger balance, "
           "and a report figure is always a formula of ledger and plan figures.", "",
           "## Reported figures: one name, one calculation, one function", "",
           "Every figure a screen shows is listed here once. **From** says which layer its inputs come from. "
           "A figure with a calculation is a formula of other figures in these tables and is never computed "
           "a second way; **Function** is the one piece of code that computes it. Screens show the "
           "calculation under the figure.", ""]
    for layer, title in ((LEDGER, "From the ledger — real money"), (PLAN, "From the plan — what-if"),
                         (BOTH, "Ledger + Plan — real money after your plans")):
        out += [f"### {title}", "", "| Figure | Meaning | How it is calculated | Function |", "|---|---|---|---|"]
        for f in FIGURES.values():
            if f.layer == layer:
                calc = f.formula or "Read directly from the " + ("ledger" if layer == LEDGER else "plan")
                out.append(f"| **{f.label}** | {f.meaning} | {calc} | `{short(f.function)}` |")
        out.append("")
    out += ["### Entry-form fields", "", "Forms that record values use the same field names everywhere.", "",
            "| Field | Layer | Meaning | Replaces |", "|---|---|---|---|"]
    out += [f"| **{name}** | {layer} | {meaning} | {old or '—'} |" for name, layer, meaning, old in FIELDS]
    out += ["", "### Retired names", "", "These names no longer appear on screens. Each is now called:", "",
            "| Old name | Now |", "|---|---|"]
    out += [f"| {old} | {FIGURES[key].label} |" for old, key in RETIRED_NAMES.items()]
    return "\n".join(out) + "\n"


START, END = "<!-- figures:start (generated by python -m lightning.core.figures) -->", "<!-- figures:end -->"

if __name__ == "__main__":  # rewrite the generated section of docs/GLOSSARY.md
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "docs" / "GLOSSARY.md"
    text = path.read_text()
    head, rest = text.split(START, 1)
    path.write_text(head + START + "\n" + glossary_markdown() + END + rest.split(END, 1)[1])
