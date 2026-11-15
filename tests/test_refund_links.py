"""NF-12AK3 (#644, owner decisions 2026-11-13): a refund names its purchase. Estimates count a linked refund in the
purchase's month; Cash and Spent keep the refund's real date; unlinking restores it; over-linking is refused."""
from decimal import Decimal

import pytest

from lightning.core.dates import parse_month
from lightning.core.errors import ConflictError, NotFoundError, ValidationError


def _ids(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id, c.categories.get_by_code("EXP.WORK.TRANSPORT").id


def _basis(c, month):
    return c.budgets.estimate_spending(*parse_month(month))


def _spent(c, category_id, month):
    return c.budgets.owned_spending(*parse_month(month)).get(category_id, Decimal(0))


def test_a_linked_refund_counts_in_its_purchase_month(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    c.transactions.record_outflow("2026-08-05", accounts["cib"].id, "1000", food)  # history before the window
    purchase = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "6000", food)
    c.transactions.record_outflow("2026-11-03", accounts["cib"].id, "500", food)
    refund = c.transactions.record_refund("2026-11-12", accounts["cib"].id, "6000", food)
    link = c.refunds.link(refund.id, purchase.id)
    assert link["amount"] == Decimal("6000")
    assert _basis(c, "2026-09").get(food, 0) == 0  # 6,000 out, 6,000 back: nothing spent in September
    assert _basis(c, "2026-11")[food] == Decimal("500")  # November keeps only its own spending
    assert (_spent(c, food, "2026-09"), _spent(c, food, "2026-11")) == (Decimal("6000"), Decimal("-5500"))
    assert c.refunds.refunded_purchase(refund.id)["expense_id"] == purchase.id
    assert [r["refund_id"] for r in c.refunds.refunds_of(purchase.id)] == [refund.id]

    c.refunds.unlink(refund.id)  # unlinking restores the real dates in the basis
    assert _basis(c, "2026-09")[food] == Decimal("6000")
    assert _basis(c, "2026-11")[food] == Decimal("0")  # floored, never -5,500
    assert c.refunds.refunded_purchase(refund.id) is None
    with pytest.raises(NotFoundError):
        c.refunds.unlink(refund.id)


def test_a_partial_refund_moves_only_its_amount(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    purchase = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "6000", food)
    refund = c.transactions.record_refund("2026-10-12", accounts["cib"].id, "1500", food)
    c.refunds.link(refund.id, purchase.id, "1000")
    assert _basis(c, "2026-09")[food] == Decimal("5000")
    assert _basis(c, "2026-10")[food] == Decimal("0")  # the unlinked 500 floors at zero


def test_over_linking_is_refused(c, setup):
    accounts, _ = setup
    food, work = _ids(c)
    purchase = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "1000", food)
    big = c.transactions.record_refund("2026-10-12", accounts["cib"].id, "1500", food)
    with pytest.raises(ValidationError):
        c.refunds.link(big.id, purchase.id, "1200")  # more than the purchase cost
    with pytest.raises(ValidationError):
        c.refunds.link(big.id, purchase.id, "1600")  # more than the refund
    assert c.refunds.link(big.id, purchase.id)["amount"] == Decimal("1000")  # the whole refund, capped
    second = c.transactions.record_refund("2026-10-20", accounts["cib"].id, "100", food)
    with pytest.raises(ValidationError):
        c.refunds.link(second.id, purchase.id)  # nothing left to return
    other = c.transactions.record_refund("2026-10-20", accounts["cib"].id, "100", work)
    with pytest.raises(ValidationError):
        c.refunds.link(other.id, purchase.id)  # another category
    early = c.transactions.record_refund("2026-08-20", accounts["cib"].id, "100", food)
    with pytest.raises(ValidationError):
        c.refunds.link(early.id, purchase.id)  # before the purchase
    with pytest.raises(ValidationError):
        c.refunds.link(purchase.id, purchase.id)  # a purchase is not a refund


def test_relinking_replaces_and_frees_room(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    first = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "1000", food)
    second = c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "1000", food)
    refund = c.transactions.record_refund("2026-10-12", accounts["cib"].id, "1000", food)
    c.refunds.link(refund.id, first.id)
    assert [x["id"] for x in c.refunds.candidates(refund.id)] == [second.id, first.id]  # its own link is room
    c.refunds.link(refund.id, second.id)
    assert c.refunds.refunded_purchase(refund.id)["expense_id"] == second.id
    assert c.refunds.refunds_of(first.id) == []


def test_candidates_are_the_same_category_within_six_months(c, setup):
    accounts, _ = setup
    food, work = _ids(c)
    old = c.transactions.record_outflow("2026-03-01", accounts["cib"].id, "100", food)
    recent = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "100", food)
    c.transactions.record_outflow("2026-09-03", accounts["cib"].id, "100", work)
    c.transactions.record_outflow("2026-11-01", accounts["cib"].id, "100", food)  # after the refund
    refund = c.transactions.record_refund("2026-10-12", accounts["cib"].id, "100", food)
    ids = [x["id"] for x in c.refunds.candidates(refund.id)]
    assert ids == [recent.id] and old.id not in ids


def test_a_reimbursement_receipt_cannot_also_be_a_refund_link(c, setup):
    accounts, _ = setup
    _, work = _ids(c)
    expense = c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "1200", work)
    claim = c.reimbursements.create_claim(expense.id, "1200")
    receipt = c.transactions.record_inflow("2026-11-02", accounts["cib"].id, "600", work)
    c.reimbursements.link_receipt(claim["id"], receipt.id, "600")
    with pytest.raises(ConflictError):
        c.refunds.link(receipt.id, expense.id)
    refund = c.transactions.record_refund("2026-11-05", accounts["cib"].id, "800", work)
    with pytest.raises(ValidationError):
        c.refunds.link(refund.id, expense.id, "700")  # 1,200 less the 600 already received
    c.refunds.link(refund.id, expense.id, "600")
    assert _basis(c, "2026-10")[work] == Decimal("0")


def test_link_and_unlink_undo(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    purchase = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "600", food)
    refund = c.transactions.record_refund("2026-10-12", accounts["cib"].id, "600", food)
    c.refunds.link(refund.id, purchase.id)
    c.undo.replay()
    assert c.refunds.refunded_purchase(refund.id) is None


# --------------------------------------------------------------------------- screens (PC and phone, EN and AR)
from fastapi.testclient import TestClient  # noqa: E402

from lightning.ui.web import create_app  # noqa: E402
from tests.screens import visible_text  # noqa: E402


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


@pytest.mark.parametrize("phone", [False, True])
def test_link_a_refund_and_record_one_through_the_screens(c, setup, phone):
    accounts, _ = setup
    food, _ = _ids(c)
    purchase = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "6000", food, description="Laptop")
    refund = c.transactions.record_refund("2026-11-12", accounts["cib"].id, "4000", food)
    client = _client(c, phone)
    page = visible_text(client.get(f"/transactions/{refund.id}").text)
    assert "This refunds…" in page and "Laptop" in page
    assert client.post(f"/transactions/{refund.id}/refund-link",
                       data={"action": "link", "expense_id": str(purchase.id)}).status_code == 303
    assert c.refunds.refunded_purchase(refund.id)["expense_id"] == purchase.id
    page = visible_text(client.get(f"/transactions/{purchase.id}").text)
    assert "Refunds" in page and "2,000.00 not returned" in page and "Record a refund" in page
    assert client.post(f"/transactions/{purchase.id}/refund",
                       data={"date": "2026-11-20", "amount": "2000"}).status_code == 303
    assert sum(r["amount"] for r in c.refunds.refunds_of(purchase.id)) == Decimal("6000")
    assert "Fully returned" in visible_text(client.get(f"/transactions/{purchase.id}").text)
    assert c.budgets.estimate_spending(*parse_month("2026-09")).get(food, 0) == 0
    over = client.post(f"/transactions/{refund.id}/refund-link", data={"action": "link", "expense_id": str(purchase.id),
                                                                       "amount": "9000"})
    assert over.status_code == 303 and c.refunds.refunded_purchase(refund.id)["amount"] == Decimal("4000")
    assert client.post(f"/transactions/{refund.id}/refund-link", data={"action": "unlink"}).status_code == 303
    assert c.refunds.refunded_purchase(refund.id) is None


@pytest.mark.parametrize("phone", [False, True])
def test_the_refund_panel_reads_arabic(c, setup, phone):
    accounts, _ = setup
    food, _ = _ids(c)
    purchase = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "6000", food)
    refund = c.transactions.record_refund("2026-11-12", accounts["cib"].id, "1000", food)
    c.refunds.link(refund.id, purchase.id)
    client = _client(c, phone, "ar")
    assert "ده استرداد لـ…" in visible_text(client.get(f"/transactions/{refund.id}").text)
    page = visible_text(client.get(f"/transactions/{purchase.id}").text)
    assert "الاستردادات" in page and "سجّل استرداد" in page
