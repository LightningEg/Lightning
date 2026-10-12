"""Numbers the 2026-10-05 routine audit found wrong, each reproduced before its fix.

The audit is quoted in each test's docstring by its number (#1 is the worst).
"""
from __future__ import annotations

from decimal import Decimal

from lightning.core.ledger import Effect, PostingLine
from lightning.core.refs import DocType

D = Decimal


def _shared_broker(c):
    """A brokerage holding one share in which you own some units and Dad owns the rest."""
    broker = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "0")
    dad = c.counterparties.create("Dad")
    income = c.categories.get_by_code("EXP.WORK.SALARY")
    cash = c.assets.cash_asset("EGP")
    c.transactions.post(DocType.IN, "2026-09-10", [
        PostingLine.cash(broker.id, cash.id, D("5000"), Effect.INFLOW, income.id, memo="Dad cash", owner_id=dad)])
    c.transactions.record_inflow("2026-09-10", broker.id, "5000", income.id, description="My cash")
    share = c.assets.create_investment("Shared share", "STOCK", "SHARED")
    return broker, dad, share


def test_1_your_share_of_a_shared_holding_is_yours_not_dads(c):
    """#1: you own 7 units and Dad owns 3, at price 200. Your holding is 1,400, not Dad's 600."""
    broker, dad, share = _shared_broker(c)
    c.investments.buy("2026-09-11", broker.id, share.id, "7", "100")
    c.investments.buy("2026-09-11", broker.id, share.id, "3", "100", owner_id=dad)
    c.assets.set_price(share.id, "2026-09-12", "200")

    holdings, _ = c.position.owned_holdings("2026-09-12")
    mine = next(h for h in holdings if h.asset_id == share.id)
    assert mine.quantity == 7
    assert mine.value == D("1400")


def test_2_your_cost_comes_from_your_own_purchases(c):
    """#2: you buy 10 @ 100 and Dad buys 10 @ 200, price 150. Your cost is 1,000, so your gain is +500."""
    broker, dad, share = _shared_broker(c)
    c.investments.buy("2026-09-11", broker.id, share.id, "10", "100")
    c.investments.buy("2026-09-11", broker.id, share.id, "10", "200", owner_id=dad)
    c.assets.set_price(share.id, "2026-09-12", "150")

    position = next(p for p in c.investments.portfolio("2026-09-12").positions if p.asset_id == share.id)
    assert position.quantity == 20 and position.cost_basis == D("3000")
    assert position.owned_quantity == 10
    assert position.owned_cost_basis == D("1000")


def test_3_old_unmarked_paydays_are_not_this_months_income(c, setup, monkeypatch):
    """#3: a 20,000 salary since June with nothing marked received: October income is 20,000, not 100,000."""
    from datetime import date
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-28")
    c.planning.create(kind="INCOME", name="Salary", amount="20000", frequency="MONTHLY", start_date="2026-06-25")
    october = c.forecaster.forecast(date(2026, 10, 28), months=2).months[0]
    assert october.income == D("20000")


def test_7_the_forecast_budget_is_the_budget_screens_left_in_plan(c, setup, monkeypatch):
    """#7: background estimates count in Left in plan, so the forecast's budget spending matches the Budget screen."""
    from datetime import date
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-01")
    accounts, cats = setup
    cib, food = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"]
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    c.budgets.set_budget(food.id, "2026-10", "8000")
    for month in ("2026-07", "2026-08", "2026-09"):  # untracked transport: a background estimate of 3,000
        c.transactions.record_outflow(f"{month}-15", cib, "3000", transport.id)
    summary = c.budgets.plan_summary("2026-10")
    assert summary["left"] == D("11000")
    october = c.forecaster.forecast(date(2026, 10, 1), months=2).months[0]
    assert october.budget_spending == summary["left"]


def test_8_a_funded_goal_that_was_partly_spent_is_not_saved_for_again(c, setup, monkeypatch):
    """#8: a goal funded in full and partly spent reads 100% funded; the forecast must not save for it again."""
    from datetime import date
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-01")
    accounts, cats = setup
    goal = c.reserves.create("Sahel trip", "4000", due_date="2026-12-31")["id"]
    c.reserves.allocate(goal, "4000")
    spent = c.transactions.record_outflow("2026-10-01", accounts["cib"].id, "1500", cats["EXP.PERSONAL.FOOD"].id)
    c.reserves.set_expense_link(goal, spent.id, "1500")
    october = c.forecaster.forecast(date(2026, 10, 1), months=2).months[0]
    assert october.goal_saving == 0


def test_4_a_partial_loan_payment_leaves_the_rest_still_to_pay(c, setup, monkeypatch):
    """#4: a 4 × 2,500 loan with 1,000 paid on the first instalment still owes 9,000, not 7,500."""
    from datetime import date
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, _ = setup
    loans = c.categories.get_by_code("EXP.PERSONAL.FOOD")  # any spending category for the payment
    item = c.planning.create(kind="LOAN", name="Phone", amount="2500", frequency="MONTHLY",
                             start_date="2026-10-05", payment_count="4", category_id=str(loans.id))
    c.planning.record_payment(item, "2026-10-05", "2026-10-05", "1000", accounts["cib"].id)
    day = date(2026, 10, 6)
    assert c.planning.what_you_owe(day).loans_still_to_pay == D("9000")
    progress = c.planning.loan_progress(c.planning.get(item), day)
    assert progress["still_to_pay"] == D("9000") and progress["paid_amount"] == D("1000")
    assert progress["paid_amount"] + progress["still_to_pay"] == progress["total_amount"]


def test_9_a_skipped_payment_stays_owed_on_a_loan_with_an_end_date(c, setup, monkeypatch):
    """#9: a loan of 2,500 a month to 2027-01-05 (4 payments) with one skipped still owes 10,000."""
    from datetime import date
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    item = c.planning.create(kind="LOAN", name="Car", amount="2500", frequency="MONTHLY",
                             start_date="2026-10-05", end_date="2027-01-05")
    day = date(2026, 10, 6)
    assert c.planning.what_you_owe(day).loans_still_to_pay == D("10000")
    c.planning.skip(item, "2026-10-05")
    assert c.planning.what_you_owe(day).loans_still_to_pay == D("10000")
    assert c.planning.loan_progress(c.planning.get(item), day)["last_date"] == "2027-02-05"


def test_10_already_paid_keeps_the_number_of_payments(c, setup, monkeypatch):
    """#10: a 6-payment plan whose first two dates were already paid keeps 6 payments in all, not 8."""
    from datetime import date
    from lightning.planning.schedule import payment_dates
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    item = c.planning.create(kind="BILL", name="Course", amount="1000", frequency="MONTHLY",
                             start_date="2026-08-20", payment_count="6")
    assert c.planning.start_after_paid(item, date(2026, 10, 6)) == "2026-10-20"
    remaining = payment_dates(c.planning.get(item), "2099-12-31")
    assert [d for _, d in remaining] == ["2026-10-20", "2026-11-20", "2026-12-20", "2027-01-20"]


def test_6_buying_a_certificate_is_money_added_to_investments(c, setup):
    """#6: certificates are investments (owner decision 2026-10-04), so buying one adds money."""
    from lightning.investments.report import investment_period
    accounts, _ = setup
    c.deposits.purchase(accounts["cd"].id, name="CIB 1-year certificate", start_date="2026-09-01",
                        lockup_end_date="2027-03-01", maturity_date="2027-09-01", principal="5000",
                        annual_rate="12.5", interest_method="SIMPLE", payout_frequency="MONTHLY",
                        compounding_frequency="MONTHLY", destination_account_id=accounts["cib"].id,
                        funding_account_id=accounts["cib"].id)
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-09-01", "2026-09-30")
    assert report["new_money"] == D("5000")


def test_5_a_return_that_rounds_to_zero_never_reads_minus_zero():
    """#5 (display): a certificate's XIRR showed "−0.0%"."""
    from lightning.ui.web import _signed_pct
    assert _signed_pct(D("-0.04")) == "0.0" and _signed_pct(D("0.04")) == "0.0"
    assert _signed_pct(D("6.2")) == "+6.2" and _signed_pct(D("-1.5")) == "−1.5"


def test_13_14_a_flat_recorded_this_month_is_a_holding_not_growth(c, monkeypatch):
    """#13: the horizon split leaves out the flat. #14: its opening balance shows as +400,000 in value."""
    import re

    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    broker = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "20000")
    share = c.assets.create_investment("A share", "STOCK", "ASHR")
    c.investments.buy("2026-09-05", broker.id, share.id, "100", "100")
    c.assets.set_price(share.id, "2026-10-15", "100")
    c.account_flows.open_account("Flat", "OTHER_ASSET", "2026-10-10", "400000")

    html = TestClient(create_app(c)).get("/investments?period=month&month=2026-10").text
    assert "410,000" in html  # the flat counts in holdings value
    assert "Intended investment horizon" not in html  # all of it unassigned: no section to say so (UX plan 10)
    marker = "Money in and out, and change in value by asset class"
    flows = html[html.index(marker):html.index(marker) + 3000]
    assert "400,000" not in flows  # the flat's opening balance is not a change in its value


def test_15_a_closed_brokerage_keeps_its_past_cash(c, setup):
    """#15: a brokerage deactivated after its cash moved out still had that cash on earlier dates."""
    accounts, _ = setup
    broker = c.account_flows.open_account("Old broker", "BROKERAGE", "2026-09-01", "5000")
    c.transactions.record_transfer("2026-10-01", broker.id, accounts["cib"].id, "5000")
    c.account_flows.deactivate(broker.id)
    assert c.reporting.owned_brokerage_cash("2026-09-15") == D("5000")
    assert c.reporting.owned_brokerage_cash("2026-10-15") == 0
    assert all(row["id"] != broker.id for row in c.reporting.owned_brokerage_cash_by_account("2026-10-15"))


def test_11_carryover_leaves_out_one_off_spending_like_the_month_does(c, setup):
    """#11: one-off spending is left out of a month's budget, so it is left out of what carries over too."""
    accounts, cats = setup
    cib, food = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"]
    party = c.categories.create(food.id, "Wedding party")
    c.budgets.set_one_off(party.id, True)
    c.budgets.set_budget(food.id, "2026-09", "8000")
    c.transactions.record_outflow("2026-09-10", cib, "5000", food.id)
    c.transactions.record_outflow("2026-09-20", cib, "5000", party.id)
    c.budgets.set_carryover("2026-10", {food.id: True})

    def line(month):
        view = c.budgets.month_view(month)
        return next(l for s in view.sections for l in s.lines if l.category_id == food.id)

    september = line("2026-09")
    assert september.available - september.actual == D("3000")  # the one-off party is left out
    assert line("2026-10").opening_carryover == D("3000")


def _refunded_october(c, setup):
    """August: a 400 jacket. October: 1,000 of food, the jacket refunded (400 back), 2,000 salary."""
    accounts, cats = setup
    cib, food = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"]
    clothes = c.categories.get_by_code("EXP.PERSONAL.ENTERTAINMENT")
    c.transactions.record_outflow("2026-08-10", cib, "400", clothes.id, counterparty="Shop")
    c.transactions.record_outflow("2026-09-10", cib, "1000", food.id)
    c.transactions.record_outflow("2026-10-10", cib, "1000", food.id)
    c.transactions.record_refund("2026-10-12", cib, "400", clothes.id, counterparty="Shop")
    c.transactions.record_inflow("2026-10-01", cib, "2000", cats["EXP.WORK.SALARY"].id)
    return cib


def test_12_the_usual_month_counts_refunds_like_money_out(c, setup):
    """#12: a refund in a past month left that month's usual Money out too high: September is 1,000 of
    food less a 400 refund, so the usual month is (1,400 + 600) / 2 = 1,000, not 1,200."""
    from datetime import date

    from lightning.reporting.spending import spending_profile
    accounts, cats = setup
    cib, food = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"]
    fun = c.categories.get_by_code("EXP.PERSONAL.ENTERTAINMENT")
    c.transactions.record_outflow("2026-08-10", cib, "400", fun.id, counterparty="Shop")
    for month in ("08", "09", "10"):
        c.transactions.record_outflow(f"2026-{month}-11", cib, "1000", food.id)
    c.transactions.record_refund("2026-09-12", cib, "400", fun.id, counterparty="Shop")
    profile = spending_profile(c.reporting, date(2026, 10, 1), date(2026, 10, 31))
    assert profile["usual_out"] == D("1000")


def test_12_average_payment_is_the_average_of_the_payments(c, setup, monkeypatch):
    """#12: two payments of 1,000 and 200 plus a 400 refund average 600, not net Money out 800 ÷ 2."""
    import re

    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-31")
    cib = _refunded_october(c, setup)
    food = setup[1]["EXP.PERSONAL.FOOD"]
    c.transactions.record_outflow("2026-10-25", cib, "200", food.id)
    html = TestClient(create_app(c)).get("/birdview/expenses?period=month&month=2026-10").text
    card = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html[html.index("Average payment"):][:400]))
    assert "600" in card and "800" not in card.split("payment")[1][:40]


def test_12_the_money_flow_chart_balances_when_a_refund_outweighs_spending(c, setup, monkeypatch):
    """#12: the Overview's money-flow chart put more on the right (spending + kept) than on the left."""
    from datetime import date

    from lightning.ui import charts, visuals
    _refunded_october(c, setup)
    seen = {}
    monkeypatch.setattr(charts, "sankey", lambda sources, targets, hub: seen.update(s=sources, t=targets) or {})
    first, last = date(2026, 10, 1), date(2026, 10, 31)
    visuals.money_sankey(c, first, last, c.reporting.cash_flow(first, last))
    left = sum(s["value"] for s in seen["s"] if s["value"] > 0)
    right = sum(t["value"] for t in seen["t"] if t["value"] > 0)
    assert left == right and any(s["label"] == "Refunds" for s in seen["s"])


def test_a_payment_on_the_31st_returns_to_the_31st_after_a_short_month(c, setup, monkeypatch):
    """Left open by the audit: already-paid used to restart the schedule on the clamped 28th, so the
    bill stayed on the 28th for good. The intended day of the month survives the short month."""
    from datetime import date
    from lightning.planning.domain import PaymentStatus
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-02-10")
    item = c.planning.create(kind="BILL", name="Rent", amount="1000", frequency="MONTHLY", start_date="2026-01-31")
    assert c.planning.start_after_paid(item, date(2026, 2, 10)) == "2026-02-28"
    left = [p.due_date for p in c.planning.payments(c.planning.get(item), "2026-05-31", date(2026, 2, 10))
            if p.status != PaymentStatus.SKIPPED]
    assert c.planning.get(item).start_date == "2026-01-31"
    assert left == ["2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]


def test_already_paid_keeps_the_day_when_a_weekend_moves_the_payment(c, setup, monkeypatch):
    """A Friday payment moved to Thursday by the weekend rule must not move the schedule's day."""
    from datetime import date
    from lightning.planning.schedule import payment_dates
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-10")
    item = c.planning.create(kind="BILL", name="Gym", amount="500", frequency="MONTHLY",
                             start_date="2026-09-16", weekend_move="BEFORE")
    c.planning.start_after_paid(item, date(2026, 10, 10))
    start = c.planning.get(item).start_date
    assert start.endswith("-16"), start
    assert payment_dates(c.planning.get(item), "2026-12-31")[-1][1] <= "2026-12-17"


def test_a_month_without_pay_counts_as_zero_once_pay_has_started(c, setup):
    """Between jobs: the empty month lowers Average monthly income; empty months before the first pay do not."""
    accounts, cats = setup
    salary, cib = cats["EXP.WORK.SALARY"], accounts["cib"]
    for day in ("2026-07-01", "2026-08-01"):  # June (empty, before the first pay) is skipped
        c.transactions.record_inflow(day, cib.id, "30000", salary.id, description="Salary")
    average = c.budgets.income_average("2026-10")  # Jul, Aug, Sep: Sep has no pay
    assert (average.amount, average.months_counted, average.first_month, average.last_month) == (
        D("20000.00"), 3, "2026-07", "2026-09")
    assert c.budgets.income_average("2026-09").months_counted == 2  # June before the first pay is not a zero
