from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


@pytest.fixture
def b(c, setup):
    accounts, cats = setup
    g = c.categories.get_by_code
    ids = {k: g(k).id for k in ("EXP.PERSONAL", "EXP.PERSONAL.FOOD", "EXP.PERSONAL.TRANSPORT",
                                 "EXP.WORK", "EXP.WORK.SOFTWARE", "EXP.WORK.SALARY")}
    return c, accounts, ids


def line(view, code):
    return next(l for s in view.sections for l in s.lines if l.code == code)


def section(view, name):
    return next(s for s in view.sections if s.name == name)


def test_repeat_until_changed(b):
    c, _, ids = b
    c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-07", "6,000")
    assert line(c.budgets.month_view("2026-06"), "EXP.PERSONAL.FOOD").budget is None
    for m in ("2026-07", "2026-08", "2027-01"):
        assert line(c.budgets.month_view(m), "EXP.PERSONAL.FOOD").budget == Decimal("6000")
    c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-09", "7000")
    assert line(c.budgets.month_view("2026-08"), "EXP.PERSONAL.FOOD").budget == Decimal("6000")
    assert line(c.budgets.month_view("2026-12"), "EXP.PERSONAL.FOOD").budget == Decimal("7000")
    c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-11", "")  # no budget from November
    assert line(c.budgets.month_view("2026-12"), "EXP.PERSONAL.FOOD").budget is None
    assert line(c.budgets.month_view("2026-10"), "EXP.PERSONAL.FOOD").budget == Decimal("7000")


def test_this_month_only(b):
    c, _, ids = b
    c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-07", "6000")
    c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-09", "9000", only_this_month=True)
    sep = line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD")
    assert sep.budget == Decimal("9000") and sep.one_off
    assert line(c.budgets.month_view("2026-10"), "EXP.PERSONAL.FOOD").budget == Decimal("6000")
    # setting it back to the repeating amount removes the override
    c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-09", "6000", only_this_month=True)
    assert not line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD").one_off
    # a one-off "no budget"
    c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-09", "", only_this_month=True)
    assert line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD").budget is None
    assert line(c.budgets.month_view("2026-10"), "EXP.PERSONAL.FOOD").budget == Decimal("6000")


def test_group_is_sum_of_categories_or_its_own_ceiling(b):
    c, _, ids = b
    c.budgets.save_month("2026-09", {ids["EXP.PERSONAL.FOOD"]: "6000", ids["EXP.PERSONAL.TRANSPORT"]: "2000"})
    view = c.budgets.month_view("2026-09")
    assert line(view, "EXP.PERSONAL").budget == Decimal("8000") and line(view, "EXP.PERSONAL").direct is None
    c.budgets.set_budget(ids["EXP.PERSONAL"], "2026-09", "20000")
    view = c.budgets.month_view("2026-09")
    assert line(view, "EXP.PERSONAL").budget == Decimal("20000")
    assert section(view, "Personal").budget == Decimal("20000")  # categories are inside, not added on top
    assert not view.warnings
    c.budgets.set_budget(ids["EXP.PERSONAL"], "2026-09", "5000")
    assert "more than its budget" in c.budgets.month_view("2026-09").warnings[0]


def test_actuals_roll_up_and_sections_are_separate(b):
    c, accounts, ids = b
    cib = accounts["cib"].id
    c.transactions.record_outflow("2026-09-05", cib, "1500", ids["EXP.PERSONAL.FOOD"])
    c.transactions.record_outflow("2026-09-06", cib, "300", ids["EXP.PERSONAL.TRANSPORT"])
    c.transactions.record_outflow("2026-09-07", cib, "899", ids["EXP.WORK.SOFTWARE"])
    c.transactions.record_outflow("2026-10-01", cib, "999", ids["EXP.PERSONAL.FOOD"])  # other month
    c.transactions.record_transfer("2026-09-08", cib, accounts["wallet"].id, "5000")  # never counts
    c.transactions.record_inflow("2026-09-25", cib, "42000", ids["EXP.WORK.SALARY"])
    c.budgets.save_month("2026-09", {ids["EXP.PERSONAL.FOOD"]: "1000", ids["EXP.WORK"]: "1500"})
    view = c.budgets.month_view("2026-09")
    food = line(view, "EXP.PERSONAL.FOOD")
    assert food.actual == Decimal("1500") and food.remaining == Decimal("-500") and food.over
    assert line(view, "EXP.PERSONAL").actual == Decimal("1800")
    personal, work = section(view, "Personal"), section(view, "Work")
    assert (personal.budget, personal.actual) == (Decimal("1000"), Decimal("1800"))
    assert personal.unbudgeted == Decimal("300")  # transport has no budget on it or above it
    assert (work.budget, work.actual, work.unbudgeted) == (Decimal("1500"), Decimal("899"), Decimal("0"))
    assert line(view, "EXP.WORK.SOFTWARE").covered  # inside the Work budget
    assert view.income == Decimal("42000")
    assert (view.budget, view.actual) == (Decimal("2500"), Decimal("2699"))


def test_rules(b):
    c, _, ids = b
    with pytest.raises(ValidationError, match="money out"):
        c.budgets.set_budget(ids["EXP.WORK.SALARY"], "2026-09", "10")
    with pytest.raises(ValidationError, match="negative"):
        c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-09", "-1")
    with pytest.raises(ValidationError):
        c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-09", "1.234")
    with pytest.raises(ValidationError):
        c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-13", "1")
    assert c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-09", "") is False  # nothing to clear


def test_signed_carryover_and_dated_reset(b):
    c, accounts, ids = b
    food, wallet = ids["EXP.PERSONAL.FOOD"], accounts["cib"].id
    c.budgets.set_budget(food, "2026-08", "1000")
    c.transactions.record_outflow("2026-08-12", wallet, "3000", food)
    c.budgets.set_carryover("2026-09", {food: True})
    sep = line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD")
    assert sep.opening_carryover == Decimal("-2000")
    assert sep.remaining == Decimal("-1000")
    c.budgets.reset_carryover(food, "2026-09")
    assert line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD").opening_carryover == 0
    assert line(c.budgets.month_view("2026-10"), "EXP.PERSONAL.FOOD").opening_carryover == Decimal("1000")


def test_overspend_recovers_with_new_monthly_allowances_and_can_be_disabled(b):
    c, accounts, ids = b
    food, wallet = ids["EXP.PERSONAL.FOOD"], accounts["cib"].id
    c.budgets.set_budget(food, "2026-08", "1000")
    c.transactions.record_outflow("2026-08-12", wallet, "3000", food)
    c.budgets.set_carryover("2026-09", {food: True})
    assert line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD").remaining == Decimal("-1000")
    assert line(c.budgets.month_view("2026-10"), "EXP.PERSONAL.FOOD").opening_carryover == Decimal("-1000")
    c.budgets.set_carryover("2026-10", {food: False})
    assert line(c.budgets.month_view("2026-11"), "EXP.PERSONAL.FOOD").opening_carryover == 0


def test_observed_month_average_and_percentage_income_basis(b):
    c, accounts, ids = b
    food, wallet = ids["EXP.PERSONAL.FOOD"], accounts["cib"].id
    salary = ids["EXP.WORK.SALARY"]
    c.transactions.record_outflow("2026-03-03", wallet, "3000", food)
    c.transactions.record_outflow("2026-06-03", wallet, "9000", food)
    c.budgets.set_budget(food, "2026-09", "", average_months=6)
    assert line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD").budget == Decimal("6000")
    transport = ids["EXP.PERSONAL.TRANSPORT"]
    c.budgets.set_budget(transport, "2026-09", "", average_months=6)
    assert line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.TRANSPORT").budget is None
    assert c.budgets.budgeting_income("2026-09") is None
    c.transactions.record_inflow("2026-03-25", wallet, "10000", salary)
    c.transactions.record_inflow("2026-06-25", wallet, "10000", salary)
    c.settings.set("budget_income_categories", f"[{salary}]")
    c.settings.set("budget_income_months", "6")
    assert c.budgets.budgeting_income("2026-09") == Decimal("10000")
    c.budgets.set_income_percentage(food, "2026-09", "10")
    assert line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD").budget == Decimal("1000")


def test_owned_refunds_reduce_spending_but_custody_is_excluded(b):
    c, accounts, ids = b
    food, wallet = ids["EXP.PERSONAL.FOOD"], accounts["cib"].id
    c.transactions.record_outflow("2026-09-02", wallet, "1000", food)
    c.transactions.record_refund("2026-09-04", wallet, "200", food)
    dad = c.counterparties.create("Dad")
    c.transactions.record_inflow("2026-09-04", wallet, "700", ids["EXP.WORK.SALARY"], owner_id=dad)
    c.transactions.record_outflow("2026-09-05", wallet, "700", food, owner_id=dad)
    assert line(c.budgets.month_view("2026-09"), "EXP.PERSONAL.FOOD").actual == Decimal("800")


def test_budget_page(c, b):
    c, accounts, ids = b
    client = TestClient(create_app(c))
    page = client.get("/budget?month=2026-09")
    assert page.status_code == 200 and "Personal" in page.text and "Work" in page.text
    r = client.post("/budget?month=2026-09", data={f"b_{ids['EXP.PERSONAL.FOOD']}": "6,000",
                                                   f"b_{ids['EXP.WORK']}": "1500"})
    assert "Saved 2 budgets from 2026-09 onward" in r.text and 'value="6,000.00"' in r.text
    r = client.post("/budget?month=2026-09", data={f"b_{ids['EXP.PERSONAL.FOOD']}": "6,000.00"})
    assert "Nothing changed" in r.text
    r = client.post("/budget?month=2026-09", data={f"b_{ids['EXP.PERSONAL.FOOD']}": "abc"})
    assert r.status_code == 400 and "not a valid number" in r.text
    assert 'value="6,000.00"' in client.get("/budget?month=2026-09").text


def test_current_month_uses_full_month_limit_before_month_end(c, b, monkeypatch):
    _, _, ids = b
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-15")
    c.budgets.set_budget(ids["EXP.PERSONAL"], "2026-09", "6000")
    page = TestClient(create_app(c)).get("/budget?period=month&month=2026-09")
    assert page.status_code == 200
    assert page.text.count("6,000") >= 2  # headline and matching group limit


def test_a_budget_row_left_reads_as_the_rounded_figures_beside_it(c, b, monkeypatch):
    c, accounts, ids = b
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-15")
    c.budgets.set_budget(ids["EXP.PERSONAL.FOOD"], "2026-09", "671")
    c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "633.50", ids["EXP.PERSONAL.FOOD"])
    page = TestClient(create_app(c)).get("/budget?period=month&month=2026-09").text
    assert "+37" in page.replace("&#43;", "+") or ">37<" in page  # 671 − 634, not 37.50 rounded up to 38
    assert "+38" not in page.replace("&#43;", "+")
