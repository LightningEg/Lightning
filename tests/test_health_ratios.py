"""Debt and fixed-cost ratios (lightning/planning/health.py) and the cards that show them."""

from datetime import date
from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.planning.domain import Frequency, PlanKind, PlannedItem, per_year
from lightning.ui.web import create_app

TODAY = date(2026, 12, 31)  # tests/conftest.py pins today


def _item(frequency, amount="1200", interval=1):
    return PlannedItem(1, PlanKind.BILL, "x", D(amount), frequency, interval, "2026-01-01", None, None,
                       None, None, None, None, True, "")


def test_a_repeating_item_comes_to_a_year():
    assert [per_year(_item(f)) for f in (Frequency.WEEKLY, Frequency.MONTHLY, Frequency.QUARTERLY,
                                        Frequency.YEARLY, Frequency.ONCE)] == [D("62400"), D("14400"), D("4800"), D("1200"), 0]
    assert per_year(_item(Frequency.MONTHLY, interval=2)) == D("7200")  # every two months


def test_nothing_owed_and_no_income_measured(c, setup):
    h = c.health.at(TODAY)
    assert (h.debt_to_net_worth.percent, h.debt_to_cash.percent) == (D("0"), D("0"))
    assert h.loan_payments_to_income.percent is None and h.fixed_costs_to_income.percent is None  # no income yet
    page = TestClient(create_app(c)).get("/plan/loans").text
    assert page.count("Nothing owed") == 2 and "No loan payments left" in page


def test_ratios_divide_what_other_figures_already_say(c, setup):
    accounts, cats = setup
    cib, salary, food = accounts["cib"].id, cats["EXP.WORK.SALARY"], cats["EXP.PERSONAL.FOOD"]
    for month in ("09", "10", "11"):
        c.transactions.record_inflow(f"2026-{month}-01", cib, "40,000", salary.id)
    c.planning.create(kind="BILL", name="Rent", amount="10000", frequency="MONTHLY", start_date="2027-01-01",
                      category_id=str(food.id))
    c.planning.create(kind="SUBSCRIPTION", name="Gym", amount="6000", frequency="YEARLY", start_date="2027-01-01",
                      category_id=str(food.id))
    c.planning.create(kind="LOAN", name="Car", amount="4000", frequency="MONTHLY", start_date="2027-01-05",
                      payment_count="10", category_id=str(food.id))
    done = c.planning.create(kind="LOAN", name="Phone", amount="900", frequency="MONTHLY", start_date="2026-10-05",
                             payment_count="2", category_id=str(food.id))
    for due in ("2026-10-05", "2026-11-05"):
        c.planning.record_payment(done, due, due, "900", cib)  # paid off: no longer a monthly cost

    h, position = c.health.at(TODAY), c.position.at(TODAY)
    assert h.debt_to_net_worth.part == position.what_you_owe == D("40000")
    assert h.debt_to_net_worth.whole == position.net_worth and h.debt_to_cash.whole == position.cash_you_own
    assert h.debt_to_net_worth.percent == D("40000") / position.net_worth * 100
    assert (h.loans_a_month, h.bills_a_month) == (D("4000"), D("10500"))
    assert h.loan_payments_to_income.percent == D("10")   # 4,000 of 40,000
    assert h.fixed_costs_to_income.percent == D("36.25")  # (10,500 + 4,000) of 40,000

    client = TestClient(create_app(c))
    loans = client.get("/plan/loans").text
    assert "Loan payments to income" in loans and "4,000 a month of 40,000 income" in loans
    recurring = client.get("/plan/recurring").text
    assert "Fixed costs to income" in recurring and "14,500 a month of 40,000 income" in recurring
    assert 'kc-figure">10,500<small>' in recurring  # Bills and subscriptions a month in whole EGP (A16), the total the ratio uses


def test_owing_more_than_you_own_is_said_not_divided(c, setup):
    accounts, cats = setup
    c.planning.create(kind="LOAN", name="Flat", amount="50000", frequency="MONTHLY", start_date="2027-01-05",
                      payment_count="40", category_id=str(cats["EXP.PERSONAL.FOOD"].id))
    h = c.health.at(TODAY)
    assert c.position.at(TODAY).net_worth < 0 and h.debt_to_net_worth.percent is None
    page = TestClient(create_app(c)).get("/plan/loans").text
    assert "You owe more than you own" in page and "tone-over" in page
