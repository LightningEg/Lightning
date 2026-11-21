"""NF-12AK5 (#648, owner decisions 2026-11-13): paid · returned · expected back · yours, and the unusual-purchase review.

The four figures match the claims service (receipts counted, open claims outstanding) plus the refunds that name
the purchase. Budget asks once about a purchase over half its category's averaging window, "Food's average includes
a 9,000 purchase on 3 Nov: leave it out of estimates?"; Keep is remembered, Leave out is undoable. Never automatic.
Tests run on 31 Dec 2026, so the three-month window is Sep to Nov."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.budgeting.recoveries import ExpenseRecoveries
from lightning.core.dates import parse_month
from lightning.ui.web import create_app
from tests.screens import visible_text


def _food(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id


def _recoveries(c):
    return ExpenseRecoveries(c.db, c.reimbursements, c.refunds)


def _client(c, phone=False, locale="en"):
    app = create_app(c)
    if phone:
        inner = app

        async def phone_app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    client = TestClient(app, follow_redirects=False)
    if locale != "en":
        assert client.post("/settings/locale", data={"locale": locale}).status_code == 303
    return client


def test_the_four_figures_match_the_claims_service(c, setup):
    accounts, _ = setup
    food = _food(c)
    purchase = c.transactions.record_outflow("2026-12-02", accounts["cib"].id, "1200", food, description="Team lunch")
    assert _recoveries(c).of(purchase.id) is None  # nothing back, nothing expected: no panel
    claim = c.reimbursements.create_claim(purchase.id, "1000")
    figures = _recoveries(c).of(purchase.id)
    assert figures == {"paid": Decimal("1200"), "returned": Decimal("0"), "expected": Decimal("1000"),
                       "yours": Decimal("200")}
    receipt = c.transactions.record_inflow("2026-12-10", accounts["cib"].id, "400",
                                           c.categories.get_by_code("EXP.WORK.SALARY").id)
    c.reimbursements.link_receipt(claim["id"], receipt.id, "400")
    refund = c.transactions.record_refund("2026-12-12", accounts["cib"].id, "100", food)
    c.refunds.link(refund.id, purchase.id)
    figures = _recoveries(c).of(purchase.id)
    listed = next(row for row in c.reimbursements.list_claims() if row["id"] == claim["id"])
    assert figures["expected"] == listed["outstanding"] == Decimal("600")
    assert figures["returned"] == listed["received"] + Decimal("100") == Decimal("500")
    assert figures["yours"] == Decimal("100")
    total = _recoveries(c).for_categories({food}, *parse_month("2026-12"))
    assert (total["paid"], total["returned"], total["expected"], total["yours"], total["count"]) == (
        Decimal("1200.00"), Decimal("500.00"), Decimal("600.00"), Decimal("100.00"), 1)


@pytest.mark.parametrize("phone", [False, True])
def test_the_transaction_and_the_category_sheet_show_them(c, setup, phone):
    accounts, _ = setup
    food = _food(c)
    purchase = c.transactions.record_outflow("2026-12-02", accounts["cib"].id, "1200", food, description="Team lunch")
    c.reimbursements.create_claim(purchase.id, "1200")
    client = _client(c, phone)
    page = visible_text(client.get(f"/transactions/{purchase.id}").text)
    assert "Money back" in page and "Expected back" in page and "1,200" in page
    sheet = visible_text(client.get(f"/budget/category/{food}/sheet?month=2026-12").text)
    assert "Money back" in sheet and "1 purchase this month" in sheet and "Expected back" in sheet
    arabic = _client(c, phone, "ar")
    assert "مستني يرجع" in visible_text(arabic.get(f"/transactions/{purchase.id}").text)


def _laptop(c, setup):
    accounts, _ = setup
    food = _food(c)
    c.transactions.record_outflow("2026-08-05", accounts["cib"].id, "1000", food)  # history before the window
    for month in ("09", "10", "11"):
        c.transactions.record_outflow(f"2026-{month}-05", accounts["cib"].id, "1000", food)
    laptop = c.transactions.record_outflow("2026-11-03", accounts["cib"].id, "9000", food, description="Laptop")
    return food, laptop


def test_the_review_asks_about_one_large_purchase(c, setup):
    food, laptop = _laptop(c, setup)
    review = c.budgets.estimate_review("2026-12")
    assert (review["transaction_id"], review["amount"], review["category_id"]) == (laptop.id, Decimal("9000"), food)
    assert c.db.scalar("SELECT COUNT(*) FROM budget_estimate_exclusions") == 0  # never automatic


def test_no_review_without_a_purchase_over_half(c, setup):
    accounts, _ = setup
    food = _food(c)
    for month in ("09", "10", "11"):
        c.transactions.record_outflow(f"2026-{month}-05", accounts["cib"].id, "1000", food)
    assert c.budgets.estimate_review("2026-12") is None
    only = c.categories.get_by_code("EXP.WORK.TRANSPORT").id  # a category's only purchase is not "unusual"
    c.transactions.record_outflow("2026-10-09", accounts["cib"].id, "5000", only)
    assert c.budgets.estimate_review("2026-12") is None


@pytest.mark.parametrize("phone", [False, True])
def test_keep_and_leave_out_through_the_screens(c, setup, phone):
    food, laptop = _laptop(c, setup)
    client = _client(c, phone)
    page = visible_text(client.get("/budget?month=2026-12").text)
    assert "average includes a 9,000 purchase" in page and "Leave it out" in page
    assert client.post("/budget/estimate-review", data={"transaction_id": str(laptop.id), "action": "keep",
                                                       "month": "2026-12"}).status_code == 303
    assert c.budgets.estimate_review("2026-12") is None
    assert "average includes" not in visible_text(client.get("/budget?month=2026-12").text)
    c.settings.set(c.budgets.REVIEW_KEPT, "[]")
    assert client.post("/budget/estimate-review", data={"transaction_id": str(laptop.id), "action": "leave_out",
                                                       "month": "2026-12"}).status_code == 303
    assert c.budgets.is_left_out(laptop.id) and c.budgets.estimate_review("2026-12") is None


def test_keep_is_remembered_and_both_choices_are_undoable(c, setup):
    food, laptop = _laptop(c, setup)
    c.budgets.keep_in_estimates(laptop.id)
    assert c.budgets.estimate_review("2026-12") is None
    c.undo.replay()  # Keep can be taken back: the question returns
    assert c.budgets.estimate_review("2026-12")["transaction_id"] == laptop.id
    c.budgets.set_left_out(laptop.id, True)
    assert c.budgets.estimate_review("2026-12") is None
    c.undo.replay()
    assert not c.budgets.is_left_out(laptop.id)


def test_the_review_reads_arabic(c, setup):
    _laptop(c, setup)
    page = visible_text(_client(c, False, "ar").get("/budget?month=2026-12").text)
    assert "تستبعده من التقديرات؟" in page and "استبعده" in page
