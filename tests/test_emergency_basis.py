"""The emergency fund in months of spending (the default) or months of spending (Settings › Budget)."""

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


@pytest.fixture
def household(c, setup):
    """Salary 30,000 and spending 15,000 a month for September to November (today is 2026-12-31), with
    a 20,000 one-off trip in October and 45,000 in the emergency fund."""
    accounts, cats = setup
    cib, salary, food = accounts["cib"].id, cats["EXP.WORK.SALARY"], cats["EXP.PERSONAL.FOOD"]
    housing = c.categories.get_by_code("EXP.PERSONAL.HOUSING")
    trip = c.categories.create(c.categories.get(food.parent_id).id, "Sahel trip")
    c.budgets.set_one_off(trip.id, True)
    for month in ("09", "10", "11"):
        c.transactions.record_inflow(f"2026-{month}-01", cib, "30,000", salary.id)
        c.transactions.record_outflow(f"2026-{month}-05", cib, "9,000", housing.id)
        c.transactions.record_outflow(f"2026-{month}-15", cib, "6,000", food.id)
    c.transactions.record_outflow("2026-10-20", cib, "20,000", trip.id)
    c.reserves.set_emergency_fund("45,000")
    return c


def test_spending_is_default_and_income_remains_an_explicit_choice(household):
    c = household
    assert c.budgets.emergency_basis() == "spending"
    c.budgets.set_emergency_basis("income")
    fund = c.budgets.emergency_fund("2026-12", D("45000"), schedule=c.schedules.view())
    assert (fund.basis, fund.monthly, fund.months, fund.target) == ("income", D("30000"), D("1.5"), D("180000"))

    c.budgets.set_emergency_basis("spending")
    spending = c.budgets.spending_average("2026-12")
    assert (spending.amount, spending.months_counted, spending.window) == (D("15000"), 3, "2026-09 to 2026-11")
    fund = c.budgets.emergency_fund("2026-12", D("45000"), schedule=c.schedules.view())  # the one-off trip is left out, as in the budget
    assert (fund.basis, fund.monthly, fund.months, fund.target) == ("spending", D("15000"), D("3"), D("90000"))

    with pytest.raises(ValidationError, match="months of income or of spending"):
        c.budgets.set_emergency_basis("wealth")
    assert c.budgets.emergency_basis() == "spending"


def test_no_fund_or_no_history_is_not_measured(c, household):
    assert c.budgets.emergency_fund("2026-12", None, schedule=c.schedules.view()).months is None
    c.budgets.set_emergency_basis("spending")
    assert c.budgets.emergency_fund("2026-09", D("45000"), schedule=c.schedules.view()).months is None  # nothing recorded before September


def test_default_spending_basis_reaches_the_screens_and_forecast(household):
    from datetime import date

    c = household
    client = TestClient(create_app(c))
    page = client.get("/plan/reserves").text
    assert "Emergency fund covers 3.0 months" in page and "Of average monthly spending." in page
    assert 'name="emergency_basis" value="spending" checked' in client.get("/settings?section=budget").text
    # Six months at 15,000 less the 45,000 set aside, rebuilt over 24 months.
    assert c.forecaster.forecast(date(2026, 12, 31)).months[0].emergency_saving == D("1875")


def test_the_setting_is_chosen_in_settings_and_read_on_reserves(household):
    # Existing explicit income settings remain intact after the default changes.
    household.budgets.set_emergency_basis("income")
    client = TestClient(create_app(household))
    page = client.get("/plan/reserves").text
    assert "Emergency fund covers 1.5 months" in page and "Of average monthly income." in page
    assert "Counted in months of income" in page and "Towards six months of income" in page

    settings = client.get("/settings?section=budget").text
    assert 'name="emergency_basis" value="income" checked' in settings and 'value="spending">' in settings
    form = {"income_months": "3", "carryover_month": "2026-12",
            "income_category": str(household.categories.get_by_code("EXP.WORK.SALARY").id), "emergency_basis": "spending",
            "exclusion_category": [str(i) for i in household.budgets.one_off_ids(with_children=False)]}
    assert client.post("/budget/settings/full", data=form).status_code == 200
    assert 'value="spending" checked' in client.get("/settings?section=budget").text

    page = client.get("/plan/reserves").text
    assert "Emergency fund covers 3.0 months" in page and "Of average monthly spending." in page
    assert "Counted in months of spending" in page and "Towards six months of spending" in page
    assert "Sep – Nov 2026 · 3 months with spending" in page

    # a form without the choice leaves it alone
    client.post("/budget/settings/full", data={k: v for k, v in form.items() if k != "emergency_basis"})
    assert household.budgets.emergency_basis() == "spending"
    refused = client.post("/budget/settings/full", data={**form, "emergency_basis": "wealth"})
    assert "/settings?section=budget" in str(refused.url) and "months of income or of spending" in refused.text
    assert household.budgets.emergency_basis() == "spending"
