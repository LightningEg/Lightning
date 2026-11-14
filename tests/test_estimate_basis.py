"""NF-12AK1 (#640, owner decisions 2026-11-13): budget estimates read their own basis. Money back linked to its
expense counts in the expense's month; a month never goes below zero; occasional spending is averaged over the whole
window once the profile covers it. Cash and Spent keep the real dates."""
from decimal import Decimal

from lightning.core.dates import parse_month
from lightning.ui.web import create_app
from tests.screens import _ScreenClient, visible_text


def _ids(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id, c.categories.get_by_code("EXP.WORK.TRANSPORT").id


def _average(c, category_id, month):
    return c.budgets.category_averages(month, schedule=c.schedules.view())[category_id]


def _spent(c, category_id, month):
    return c.budgets.owned_spending(*parse_month(month)).get(category_id, Decimal(0))


def test_one_purchase_in_three_covered_months_is_a_third_a_month(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "6000", food)
    row = _average(c, food, "2026-12")  # September, October, November: the profile covers all three
    assert (row["average3"], row["observed3"], row["full3"]) == (Decimal("2000.00"), 1, True)
    newer = _average(c, food, "2026-10")  # July to September: older than the profile, so the observed month is used
    assert (newer["average3"], newer["full3"]) == (Decimal("6000.00"), False)


def test_a_refund_alone_never_makes_a_negative_month(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "6000", food)
    c.transactions.record_refund("2026-11-12", accounts["cib"].id, "6000", food)
    assert _average(c, food, "2027-01")["average3"] == Decimal("0.00")  # was -6,000
    assert _spent(c, food, "2026-11") == Decimal("-6000")  # Spent and cash keep the real date


def test_a_reimbursement_counts_in_its_expense_month(c, setup):
    accounts, _ = setup
    _, work = _ids(c)
    expense = c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "1200", work)
    claim = c.reimbursements.create_claim(expense.id, "1200")
    receipt = c.transactions.record_inflow("2026-11-02", accounts["cib"].id, "600", work)
    c.reimbursements.link_receipt(claim["id"], receipt.id, "600")
    october, november = (c.budgets.estimate_spending(*parse_month(m)) for m in ("2026-10", "2026-11"))
    assert october[work] == Decimal("600") and work not in november
    assert (_spent(c, work, "2026-10"), _spent(c, work, "2026-11")) == (Decimal("1200"), Decimal("-600"))
    c.reimbursements.unlink_receipt(claim["id"], c.reimbursements.list_claims()[0]["receipts"][0]["id"])
    assert c.budgets.estimate_spending(*parse_month("2026-10"))[work] == Decimal("1200")


def test_a_pending_claim_counts_in_full_until_money_arrives(c, setup):
    accounts, _ = setup
    _, work = _ids(c)
    expense = c.transactions.record_outflow("2026-11-02", accounts["cib"].id, "1200", work)
    c.reimbursements.create_claim(expense.id, "1200")
    assert c.budgets.estimate_spending(*parse_month("2026-11"))[work] == Decimal("1200")


def test_budget_names_the_window(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "6000", food)
    text = visible_text(_ScreenClient(create_app(c), "http://testserver").get("/budget?month=2026-12&open_group=all").text)
    assert "Food & Groceries 0 spent Track Leave outside the budget 2,000 1 of 3 months had spending" in text
