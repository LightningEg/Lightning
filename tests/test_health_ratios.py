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


def test_expired_commitments_leave_fixed_costs_but_missed_payments_are_still_owed(c, setup):
    _, cats = setup
    c.settings.set("budget_manual_monthly_income", "10000")
    c.planning.create(kind="BILL", name="Rent", amount="3000", frequency="MONTHLY", start_date="2026-10-01")
    for kind, name, bound in (("BILL", "School bus", {"payment_count": "2"}),
                              ("SUBSCRIPTION", "Gym", {"end_date": "2026-11-15"})):
        c.planning.create(kind=kind, name=name, amount="1000", frequency="MONTHLY",
                          start_date="2026-10-15", category_id=cats["EXP.PERSONAL.FOOD"].id, **bound)
    november = c.health.at(date(2026, 11, 15))
    december = c.health.at(TODAY)
    assert november.fixed_costs_to_income.percent == 50
    assert december.fixed_costs_to_income.percent == 30
    assert december.debt_to_cash.part == 13000  # three rents plus both unpaid bus and gym payments
    fixed = next(f for f in c.health.figures(TODAY) if f.key == "fixed_costs_to_income")
    assert fixed.period == "Monthly · Set by hand in Settings"


def test_refunds_above_spending_do_not_raise_a_savings_alert(c, setup):
    accounts, cats = setup
    bank = accounts["cib"].id
    c.transactions.record_inflow("2026-11-01", bank, "10000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_refund("2026-11-05", bank, "2000", cats["EXP.PERSONAL.FOOD"].id)
    saving = next(f for f in c.health.figures(TODAY) if f.key == "savings_rate")
    assert "Refunds" in saving.gap and saving.value is None
    assert saving.band is None and saving.status is None


def test_watch_is_not_counted_as_good_in_the_health_summary():
    from lightning.ui.status import health

    for alerts in ([], ["Fixed costs to income"]):
        summary = health(2, 4, alerts)
        assert summary == {"text": "{n} of {m} figures are within your limits.", "values": {"n": 2, "m": 4}}


def test_debt_meter_keeps_custom_limits_on_the_same_scale(c, setup):
    from lightning.ui.health_rows import meter

    c.health.set_limit("debt_to_cash", "80", alert_raw="200")
    debt = next(f for f in c.health.figures(TODAY) if f.key == "debt_to_cash")
    good, alert = meter(debt)["ticks"]
    assert 0 < good < alert < 100
    assert abs(good / alert - 80 / 200) < 0.00001


def test_monthly_loan_burden_reflects_a_smaller_final_instalment(c, setup):
    accounts, _ = setup
    c.settings.set("budget_manual_monthly_income", "10000")
    loan = c.planning.create(kind="LOAN", name="Phone", amount="1000", frequency="MONTHLY",
                             start_date="2027-01-05", payment_count="3")
    c.planning.record_early_payment(loan, "2750", "0", "2026-12-20", accounts["cib"].id, "3000")
    assert c.health.at(date(2026, 12, 19)).loans_a_month == 1000
    h = c.health.at(TODAY)
    assert h.debt_to_net_worth.part == 250
    assert h.loans_a_month == 250 and h.loan_payments_to_income.percent == D("2.5")
