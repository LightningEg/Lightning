"""NF-12AK5 (#648, owner 2026-11-13): a category's month reads paid · returned · expected back · yours; work claims
(NF-12AM) stay out of personal spending and are never counted twice; the sheet shows the four only when something came
or is due back."""
from decimal import Decimal

import pytest

from lightning.core.dates import parse_month
from tests.test_budget_exclusions_ui import client_for

D = Decimal


def _food(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id


def _rec(c, cid, month="2026-10"):
    first, last = parse_month(month)
    tree = c.budgets.tree_ids(cid)
    return c.budgets.recoveries(tree, first, last, expected_back=c.reimbursements.expected_back(tree, first, last))


def test_paid_returned_expected_back_and_yours(c, setup):
    accounts, _ = setup
    food = _food(c)
    c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "1000", food)
    dinner = c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "1200", food)
    c.transactions.record_refund("2026-10-09", accounts["cib"].id, "300", food)
    claim = c.reimbursements.create_claim(dinner.id, "800")  # a friend owes 800 of the dinner
    assert _rec(c, food) == {"paid": D("2200"), "returned": D("300"), "expected_back": D("800"), "yours": D("1100")}

    back = c.transactions.record_inflow("2026-10-20", accounts["cib"].id, "500", food)
    c.reimbursements.link_receipt(claim["id"], back.id, "500")
    rec = _rec(c, food)
    assert (rec["returned"], rec["expected_back"], rec["yours"]) == (D("800"), D("300"), D("1100"))
    assert rec["expected_back"] == c.reimbursements.list_claims()[0]["outstanding"]  # matches the claims service


def test_work_claims_are_not_counted_twice(c, setup):
    accounts, _ = setup
    food = _food(c)
    trip = c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "600", food)
    c.reimbursements.create_work_claim(trip.id, "600")
    assert _rec(c, food) == {"paid": D("0"), "returned": D("0"), "expected_back": D("0"), "yours": D("0")}


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("locale", ["en", "ar"])
def test_the_sheet_shows_the_four_only_when_money_comes_back(c, setup, phone, locale):
    accounts, _ = setup
    food = _food(c)
    c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "1000", food)
    client = client_for(c, phone, locale)
    assert "budget-recoveries" not in client.get(f"/budget/category/{food}/sheet?month=2026-10").text
    c.transactions.record_refund("2026-10-09", accounts["cib"].id, "250", food)
    page = client.get(f"/budget/category/{food}/sheet?month=2026-10").text
    assert "budget-recoveries" in page
    assert ("Returned" in page) == (locale == "en") and ("Yours" in page) == (locale == "en")
