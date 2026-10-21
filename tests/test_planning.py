from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.planning.domain import Frequency, PaymentStatus, PlanKind, PlannedItem, WeekendMove
from lightning.planning.schedule import describe, payment_dates
from lightning.ui.web import create_app


def _item(**kw) -> PlannedItem:
    base = dict(id=1, kind=PlanKind.BILL, name="Bill", amount=Decimal("100"), frequency=Frequency.MONTHLY,
                interval_count=1, start_date="2026-01-31", end_date=None, payment_count=None, account_id=None,
                category_id=None, counterparty_id=None, principal=None, active=True, notes="")
    return PlannedItem(**(base | kw))


# ---------------------------------------------------------------- schedule
def test_month_end_dates_clamp_to_the_last_day():
    dates = [d for _, d in payment_dates(_item(), "2026-04-30")]
    assert dates == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_payment_count_ends_a_loan_and_weekly_and_once_work():
    loan = _item(kind=PlanKind.LOAN, start_date="2026-10-05", payment_count=3)
    assert [d for _, d in payment_dates(loan, "2030-01-01")] == ["2026-10-05", "2026-11-05", "2026-12-05"]
    weekly = _item(frequency=Frequency.WEEKLY, interval_count=2, start_date="2026-09-01")
    assert [d for _, d in payment_dates(weekly, "2026-09-30")] == ["2026-09-01", "2026-09-15", "2026-09-29"]
    once = _item(frequency=Frequency.ONCE, start_date="2026-09-10")
    assert payment_dates(once, "2027-01-01") == [(1, "2026-09-10")]
    assert describe(loan) == "Monthly on day 5 · 3 payments"


def test_weekend_dates_move_to_thursday_or_sunday_or_stay():
    # 2026-10-02 is a Friday, 2026-10-03 a Saturday, 2026-07-31 a Friday at a month's end.
    salary = _item(kind=PlanKind.INCOME, start_date="2026-10-02", weekend_move=WeekendMove.BEFORE)
    assert payment_dates(salary, "2026-10-31") == [(1, "2026-10-01")]
    rent = _item(start_date="2026-10-03", weekend_move=WeekendMove.AFTER)
    assert payment_dates(rent, "2026-10-31") == [(1, "2026-10-04")]
    assert payment_dates(_item(start_date="2026-10-02"), "2026-10-31") == [(1, "2026-10-02")]
    # A Friday month-end moved after falls in the next month, and only a window that reaches it counts it.
    late = _item(start_date="2026-07-31", weekend_move=WeekendMove.AFTER, payment_count=1)
    assert payment_dates(late, "2026-07-31") == [] and payment_dates(late, "2026-08-02") == [(1, "2026-08-02")]
    assert describe(salary) == "Monthly on day 2 · Thursday if on a weekend"


def test_a_new_item_keeps_its_date_until_you_choose_and_a_paid_date_stays_paid(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, cats = setup
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    form = client.get("/plan/items/new?kind=INCOME").text
    assert 'value="none" checked' in form and "On a weekend" in form and ">Day before<" in form
    assert "Salary" in form and "Food &amp; Groceries" not in form and "System Categories" in form
    assert "Internal transfers" in form and "Capital allocation" in form and "Adjustment" in form
    food = cats["EXP.PERSONAL.FOOD"]
    item_id = c.planning.create(kind="BILL", name="Box", amount="400", frequency="MONTHLY", start_date="2026-10-02",
                                category_id=str(food.id))
    c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "400", food.id, counterparty="Box")
    assert c.planning.match_payments(date(2026, 10, 6)) == 1
    item = c.planning.get(item_id)
    c.planning.update(item_id, **{"kind": "BILL", "name": "Box", "amount": "400", "frequency": "MONTHLY",
                                "start_date": "2026-10-02", "category_id": str(food.id), "weekend_move": "before"})
    first = c.planning.payments(c.planning.get(item_id), "2026-10-31", date(2026, 10, 6))[0]
    assert item.weekend_move == WeekendMove.NONE and first.due_date == "2026-10-01"
    assert first.status == PaymentStatus.PAID  # settled under its old date, still paid after the move
    with pytest.raises(ValidationError):
        c.planning.create(kind="BILL", name="X", amount="1", frequency="MONTHLY", start_date="2026-10-02",
                          weekend_move="sideways")


# ------------------------------------------------------------ what you owe
def test_only_due_bills_and_loans_count_as_owed(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    accounts, cats = setup
    c.planning.create(kind="BILL", name="Internet", amount="650", frequency="MONTHLY", start_date="2026-09-20",
                      account_id=str(accounts["cib"].id))
    c.planning.create(kind="SUBSCRIPTION", name="Streaming", amount="120", frequency="MONTHLY",
                      start_date="2026-10-05")
    c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY", start_date="2026-09-05",
                      payment_count="4")
    owe = c.planning.what_you_owe(date(2026, 9, 30))
    # Internet (09-20) and the first loan payment (09-05) are due; streaming is upcoming.
    assert owe.bills_due == Decimal("3150")
    assert owe.loans_still_to_pay == Decimal("10000")
    assert owe.other_bills_due == Decimal("650")
    assert owe.total == Decimal("10650")  # the due loan payment is counted once


def test_loan_needs_payments_left_or_a_last_date(c):
    with pytest.raises(ValidationError):
        c.planning.create(kind="LOAN", name="Phone", amount="900", frequency="MONTHLY", start_date="2026-10-01")


# ---------------------------------------------------------------- matching
def test_a_posted_payment_settles_the_bill_and_voiding_it_reopens(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"]
    item_id = c.planning.create(kind="BILL", name="Groceries box", amount="400", frequency="MONTHLY",
                                start_date="2026-09-12", account_id=str(accounts["cib"].id),
                                category_id=str(food.id))
    txn = c.transactions.record_outflow("2026-09-13", accounts["cib"].id, "395", food.id, counterparty="Box")
    assert c.planning.match_payments(date(2026, 9, 30)) == 1
    payment = c.planning.payments(c.planning.get(item_id), "2026-09-30", date(2026, 9, 30))[0]
    assert payment.status == PaymentStatus.PAID and payment.transaction_id == txn.id
    assert c.planning.what_you_owe(date(2026, 9, 30)).bills_due == 0
    c.transactions.void(txn.id)
    payment = c.planning.payments(c.planning.get(item_id), "2026-09-30", date(2026, 9, 30))[0]
    assert payment.status == PaymentStatus.DUE


def test_two_candidates_are_left_for_the_user(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"]
    c.planning.create(kind="BILL", name="Box", amount="400", frequency="MONTHLY", start_date="2026-09-12",
                      category_id=str(food.id))
    c.transactions.record_outflow("2026-09-11", accounts["cib"].id, "400", food.id)
    c.transactions.record_outflow("2026-09-14", accounts["wallet"].id, "400", food.id)
    assert c.planning.match_payments(date(2026, 9, 30)) == 0


# ---------------------------------------------------------------- forecast
def test_forecast_counts_a_budgeted_bill_once_and_estimates_income(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-15")
    accounts, cats = setup
    salary, food = cats["EXP.WORK.SALARY"], cats["EXP.PERSONAL.FOOD"]
    c.transactions.record_inflow("2026-09-01", accounts["cib"].id, "30000", salary.id)
    c.budgets.set_budget(food.id, "2026-10", "5000")
    c.budgets.set_budget(food.id, "2026-11", "5000")
    c.planning.create(kind="BILL", name="Groceries box", amount="1200", frequency="MONTHLY", start_date="2026-11-10",
                      category_id=str(food.id))
    forecast = c.forecaster.forecast(date(2026, 10, 15), months=2)
    november = forecast.months[1]
    assert november.commitments == Decimal("1200")
    assert november.budget_spending == Decimal("3800")  # 5,000 plan less the 1,200 bill inside it
    assert november.income == Decimal("30000.00") and november.income_estimated
    assert forecast.average_income == Decimal("30000.00") and forecast.average_income_months == 1


# -------------------------------------------------------------------- screens
def test_screens_show_bills_due_and_net_worth(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    accounts, cats = setup
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    created = client.post("/plan/items", data={
        "kind": "BILL", "name": "Electricity", "amount": "480", "frequency": "MONTHLY", "interval_count": "1",
        "start_date": "2026-09-25", "account_id": str(accounts["cib"].id),
        "category_id": str(cats["EXP.PERSONAL.FOOD"].id), "counterparty": "Electricity Co", "past_due": "due"})
    assert created.status_code == 200 and "Electricity added." in created.text
    client.post("/plan/items", data={"kind": "LOAN", "name": "Car loan", "amount": "2500", "frequency": "MONTHLY",
                                     "interval_count": "1", "start_date": "2026-10-05", "payment_count": "2"})
    overview = client.get("/").text
    assert "Net worth" in overview and "What you owe" in overview and "Bills due" in overview
    assert "−5,480" in overview  # 480 due + 5,000 of loan payments still to pay
    checks = client.get("/checks").text
    assert "Free cash plus reserves and bills due equals spendable cash" in checks
    assert client.get("/reserves", follow_redirects=False).headers["location"] == "/plan/reserves"
    for page in ("/plan", "/plan/recurring", "/plan/loans", "/plan/reserves"):
        assert client.get(page).status_code == 200
    item = next(i for i in c.planning.items() if i.name == "Electricity")
    paid = client.post(f"/plan/items/{item.id}/pay", data={
        "due": "2026-09-25", "back": "/plan", "outcome": "record", "date_paid": "2026-09-26", "amount": "480",
        "account_id": str(accounts["cib"].id)}, follow_redirects=False)
    assert paid.status_code == 303 and "marked%20paid" in paid.headers["location"]
    assert c.planning.what_you_owe(date(2026, 9, 30)).bills_due == 0


def test_loan_payments_count_as_spending_and_leave_net_worth_unchanged(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-31")
    accounts, cats = setup
    loans_category = c.categories.get_by_code("EXP.SYSTEM.LOANS")
    assert loans_category.name == "Loan payments"
    item_id = c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY",
                                start_date="2026-10-05", payment_count="24", account_id=str(accounts["cib"].id))
    assert c.planning.get(item_id).category_id == loans_category.id  # default when none is chosen
    day = date(2026, 10, 31)
    before_owe = c.planning.what_you_owe(day).total
    before_net = c.reporting.net_worth(day).total - before_owe
    before_spent = c.reporting.cash_flow(date(2026, 10, 1), day).outflows
    c.planning.record_payment(item_id, "2026-10-05", "2026-10-05", "2500", None)
    after_owe = c.planning.what_you_owe(day).total
    assert c.reporting.cash_flow(date(2026, 10, 1), day).outflows - before_spent == Decimal("2500")
    assert before_owe - after_owe == Decimal("2500")
    assert c.reporting.net_worth(day).total - after_owe == before_net


def test_overview_lists_due_bills_under_needs_you(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    accounts, _ = setup
    c.planning.create(kind="BILL", name="Electricity", amount="480", frequency="MONTHLY", start_date="2026-09-25")
    c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY", start_date="2026-09-05",
                      payment_count="3")
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get("/").text
    start = page.index('<section class="needs"')
    attention = page[start:page.index("</section>", start)]  # rows under the Lead (guideline 3.33, A09)
    assert page.index("lead-card") < start < page.index('class="stat-tiles"')
    assert "Needs you" in attention and "<span>· 2</span>" in attention  # the count is every item
    # Feedback ticket 84: both are payments, so they are one row that opens their own page.
    assert "Bills and payments · 2" in attention and "Loan payment due: Car loan, Bill due: Electricity" in attention
    group = TestClient(create_app(c), base_url="http://127.0.0.1").get("/needs-you/payments").text
    assert "Bill due: Electricity" in group and "Due 2026-09-25 · 480" in group
    assert "Loan payment due: Car loan" in group and "Mark paid" in group


def test_a_due_bill_inside_a_budget_is_not_counted_twice(c, setup, monkeypatch):
    # Rent is due and unpaid: it comes off free cash as a bill due, so it must not also be
    # budget still to spend (Mohab, 2026-10-06: Safe to spend was 12,000 too low).
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, cats = setup
    housing = c.categories.get_by_code("EXP.PERSONAL.HOUSING")
    c.budgets.set_budget(housing.id, "2026-10", "12000")
    c.planning.create(kind="BILL", name="Rent", amount="12000", frequency="MONTHLY", start_date="2026-10-03",
                      category_id=str(housing.id))
    day = date(2026, 10, 6)
    october = c.forecaster.forecast(day).months[0]
    assert c.planning.what_you_owe(day).bills_due == Decimal("12000")
    assert october.budget_spending == 0
    parts = dict(c.forecaster.forecast(day).safe_to_spend_parts)
    assert "Budget until payday" not in parts  # nothing left once the due rent is counted


def test_manual_link_suggests_only_plausible_transactions(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, cats = setup
    item_id = c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY",
                                start_date="2026-10-05", payment_count="24")
    c.transactions.record_outflow("2026-09-25", accounts["cib"].id, "2000", cats["EXP.PERSONAL.FOOD"].id,
                                  counterparty="Mom")
    c.transactions.record_outflow("2026-10-04", accounts["cib"].id, "2480", cats["EXP.PERSONAL.FOOD"].id,
                                  counterparty="Toyota")
    payment = c.planning.payments(c.planning.get(item_id), "2026-10-05", date(2026, 10, 6))[0]
    amounts = [r["amount"] for r in c.planning.candidates(payment, date(2026, 10, 6), loose=True)]
    assert amounts == [Decimal("2480")]  # the 2,000 gift to Mom is not offered


def test_a_loan_adds_its_payments_as_a_budget_line(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, _ = setup
    loans = c.categories.get_by_code("EXP.SYSTEM.LOANS")
    assert not c.budgets.has_plan("2026-10")
    c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY", start_date="2026-10-05",
                      payment_count="2", account_id=str(accounts["cib"].id))
    assert not c.budgets.has_plan("2026-10")  # a loan alone does not count as having made a plan

    def line(month):
        view = c.budgets.month_view(month)
        return next(l for s in view.sections for l in s.lines if l.category_id == loans.id)
    october = line("2026-10")
    assert october.budget == Decimal("2500") and october.from_loans
    assert line("2026-11").budget == Decimal("2500")
    assert not any(l.category_id == loans.id and l.budget for s in c.budgets.month_view("2026-12").sections
                   for l in s.lines)  # the loan has ended: no plan line
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get("/budget?month=2026-10").text
    assert "Loan payments this month" in page
    c.budgets.set_budget(loans.id, "2026-10", "3000")  # a rule you set replaces the scheduled amount
    assert line("2026-10").budget == Decimal("3000") and not line("2026-10").from_loans


def test_skipping_a_loan_payment_moves_it_to_the_end(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    item_id = c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY",
                                start_date="2026-10-05", payment_count="24")
    day = date(2026, 10, 6)
    assert c.planning.what_you_owe(day).loans_still_to_pay == Decimal("60000")
    c.planning.skip(item_id, "2026-10-05")
    progress = c.planning.loan_progress(c.planning.get(item_id), day)
    assert c.planning.what_you_owe(day).loans_still_to_pay == Decimal("60000")  # still owed
    assert progress["total"] == 24 and progress["last_date"] == "2028-10-05" and len(progress["skipped"]) == 1
    c.planning.reopen(item_id, "2026-10-05")
    assert c.planning.loan_progress(c.planning.get(item_id), day)["last_date"] == "2028-09-05"


def test_lazy_input_and_next_month(c, setup, monkeypatch):
    from lightning.core.dates import parse_date
    from lightning.core.money import to_decimal
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    assert to_decimal("١٢٬٥٠٠٫٥") == Decimal("12500.5") and to_decimal("۶۰۰") == Decimal("600")
    assert parse_date("٥/١٠") == date(2026, 10, 5)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    ahead = client.get("/budget?month=2026-11", follow_redirects=False)
    assert ahead.status_code == 303 and "has%20not%20started" in ahead.headers["location"]
    item_id = c.planning.create(kind="BILL", name="Gym", amount="600", frequency="MONTHLY", start_date="2026-10-05")
    form = client.get(f"/plan/items/{item_id}/edit").text
    assert ">Delete<" in form and "cannot be undone" in form
    c.planning.skip(item_id, "2026-10-05")
    form = client.get(f"/plan/items/{item_id}/edit").text
    assert ">Stop<" in form and "First due date" in form


def test_a_past_first_date_that_was_paid_starts_from_the_next_one(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    base = {"kind": "BILL", "amount": "600", "frequency": "MONTHLY", "interval_count": "1", "start_date": "2026-10-05"}
    added = client.post("/plan/items", data={**base, "name": "Gym"}, follow_redirects=False)
    assert "next%20one%20is%20due%202026-11-05" in added.headers["location"]
    gym = next(i for i in c.planning.items() if i.name == "Gym")
    assert gym.start_date == "2026-11-05" and c.planning.what_you_owe(date(2026, 10, 6)).bills_due == 0
    client.post("/plan/items", data={**base, "name": "Club", "past_due": "due"})
    assert c.planning.what_you_owe(date(2026, 10, 6)).bills_due == Decimal("600")  # still unpaid, so due


def test_paying_a_new_amount_offers_to_plan_it_from_now_on(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, _ = setup
    housing = c.categories.get_by_code("EXP.PERSONAL.HOUSING")
    item_id = c.planning.create(kind="BILL", name="Rent", amount="12000", frequency="MONTHLY", start_date="2026-10-03",
                                account_id=str(accounts["cib"].id), category_id=str(housing.id))
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    paid = client.post(f"/plan/items/{item_id}/pay", data={"due": "2026-10-03", "back": "/plan", "outcome": "record",
                       "date_paid": "2026-10-03", "amount": "12500", "account_id": str(accounts["cib"].id)},
                       follow_redirects=False)
    assert "12%2C500.00%20from%20now%20on" in paid.headers["location"]
    page = client.get("/plan/recurring").text
    assert "Use 12,500.00 from now on" in page
    client.post(f"/plan/items/{item_id}/amount", data={"amount": "12500", "back": "/plan/recurring"})
    assert c.planning.get(item_id).amount == Decimal("12500")


def test_tiny_repeats_are_not_suggested(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, cats = setup
    for month in ("07", "08", "09"):
        c.transactions.record_outflow(f"2026-{month}-28", accounts["cib"].id, "15", cats["EXP.PERSONAL.FOOD"].id,
                                      counterparty="Bank fee")
        c.transactions.record_outflow(f"2026-{month}-20", accounts["cib"].id, "650", c.categories.get_by_code("EXP.PERSONAL.UTILITIES").id,
                                      counterparty="WE")
    names = [s["name"] for s in c.planning.suggestions(date(2026, 10, 6))]
    assert "WE" in names and "Bank fee" not in names


def test_everyday_spending_and_interest_are_not_suggested_and_a_suggestion_can_be_hidden(c, setup, monkeypatch):
    # Owner's UX plan: Carrefour belongs in the budget, and certificate interest is already in the forecast.
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, cats = setup
    for month in ("07", "08", "09"):
        for name, code in (("Carrefour", "EXP.PERSONAL.FOOD"), ("Talabat", "EXP.PERSONAL.DINING"),
                           ("Gym", "EXP.PERSONAL.HEALTH")):
            c.transactions.record_outflow(f"2026-{month}-10", accounts["cib"].id, "900", c.categories.get_by_code(code).id,
                                          counterparty=name)
        c.transactions.record_inflow(f"2026-{month}-15", accounts["cib"].id, "1833.33",
                                     cats["EXP.INVEST.INTEREST"].id, counterparty="NBE")
    assert [s["name"] for s in c.planning.suggestions(date(2026, 10, 6))] == ["Gym"]
    gym = c.planning.suggestions(date(2026, 10, 6))[0]["counterparty_id"]
    page = TestClient(create_app(c), base_url="http://127.0.0.1").post(f"/plan/suggestions/{gym}/not-recurring", follow_redirects=True)
    assert "Gym will not be suggested again." in page.text and "Looks recurring" not in page.text
    assert c.planning.suggestions(date(2026, 10, 6)) == []


def test_safe_to_spend_counts_every_month_until_the_next_income(c, setup, monkeypatch):
    # Between jobs the next pay is two months away: next month's budget still comes out of today's cash
    # (bug found 2026-10-04: only this month's budget was taken off).
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-31")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    for month in ("2026-10", "2026-11", "2026-12"):
        c.budgets.set_budget(food.id, month, "3000")
    c.planning.create(kind="INCOME", name="New job", amount="40000", frequency="MONTHLY", start_date="2026-12-16")
    f = c.forecaster.forecast(date(2026, 10, 31))
    parts = dict(f.safe_to_spend_parts)
    # All of November (3,000) and the 15 days of December before the pay (3,000 × 15/31).
    assert f.next_income_date == "2026-12-16"
    assert parts["Budget until payday"] == -(Decimal("3000") + Decimal("1451.61")) - f.months[0].budget_spending
    assert f.safe_to_spend == f.free_cash + sum(v for k, v in parts.items() if k != "Free cash")


def test_the_plan_card_and_safe_to_spend_count_the_same_payments(c, setup, monkeypatch):
    # The card used to count overdue bills (already in Bills due) and look only 30 days ahead, so with
    # the next pay two months away it disagreed with Safe to spend's own line (2026-10-04).
    import re
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-31")
    c.planning.create(kind="INCOME", name="New job", amount="40000", frequency="MONTHLY", start_date="2026-12-20")
    c.planning.create(kind="BILL", name="Gym", amount="700", frequency="MONTHLY", start_date="2026-10-20")   # overdue
    c.planning.create(kind="BILL", name="Insurance", amount="3000", frequency="ONCE", start_date="2026-12-10")
    f = c.forecaster.forecast(date(2026, 10, 31))
    part = -dict(f.safe_to_spend_parts)["Due before payday"]
    assert part == sum(p.amount for p in f.payments_before_income)
    assert "Insurance" in {p.item.name for p in f.payments_before_income}            # 40 days ahead
    assert all(p.status.value == "UPCOMING" for p in f.payments_before_income)       # the overdue Gym is in Bills due
    page = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", TestClient(create_app(c)).get("/plan").text))
    card = re.search(r"Due before payday \d+ (?:late|payments?) ([\d,]+) EGP", page)
    assert card and card.group(1) == f"{part:,.0f}"


def test_recurring_rows_put_oldest_unpaid_date_first(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-14")
    for name, due in (("ZZ overdue", "2026-10-01"), ("AA next month", "2026-11-01"),
                      ("MM next week", "2026-10-20")):
        c.planning.create(kind="BILL", name=name, amount="100", frequency="ONCE", start_date=due)
    page = TestClient(create_app(c)).get("/plan/recurring").text
    # Restrict this to the list: totals and charts also name the items.
    rows = page.split('id="recurring-list"', 1)[1]
    assert rows.index("ZZ overdue") < rows.index("MM next week") < rows.index("AA next month")


def test_a_bill_cannot_be_paid_twice_for_the_same_due_date(c, setup):
    accounts, cats = setup
    item_id = c.planning.create(kind="BILL", name="Internet", amount="650", frequency="MONTHLY",
                                start_date="2026-10-20", account_id=str(accounts["cib"].id),
                                category_id=str(cats["EXP.PERSONAL.FOOD"].id))
    day = date(2026, 10, 31)
    c.planning.record_payment(item_id, "2026-10-20", "2026-10-20", "650", None)
    spent = c.reporting.cash_flow(date(2026, 10, 1), day).outflows
    with pytest.raises(ValidationError):
        c.planning.record_payment(item_id, "2026-10-20", "2026-10-20", "650", None)
    assert c.reporting.cash_flow(date(2026, 10, 1), day).outflows == spent
    c.planning.reopen(item_id, "2026-10-20")  # after reopening it can be recorded again
    c.planning.record_payment(item_id, "2026-10-20", "2026-10-20", "650", None)
