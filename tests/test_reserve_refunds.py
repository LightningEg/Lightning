"""NF-12AK4 (#647, owner decisions 2026-11-13): a refund that names a reserve-funded purchase goes back to the reserve.

#626's case: a 1,000 purchase paid from a reserve, 200 refunded. The reserve has used 800 and still holds 200; the
month's plan spending is 0, not -200. Cash keeps the refund on its date; a refund beyond the reserve-funded part
lowers the month as before; unlinking puts everything back."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.dates import parse_month
from lightning.ui.web import create_app
from tests.screens import visible_text


def _food(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id


def _plan(c, category_id, month):
    return c.budgets.plan_funded_spending(*parse_month(month)).get(category_id, Decimal(0))


def _reserve(c, reserve_id):
    return next(r for r in c.reserves.list_active() if r["id"] == reserve_id)


def _case(c, setup, refund_amount="200", refund_date="2026-11-12", funded="1000"):
    accounts, _ = setup
    food = _food(c)
    reserve = c.reserves.create("New fridge", "1000")
    c.reserves.allocate(reserve["id"], "1000")
    purchase = c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "1000", food, description="Fridge")
    c.reserves.set_expense_link(reserve["id"], purchase.id, funded)
    refund = c.transactions.record_refund(refund_date, accounts["cib"].id, refund_amount, food)
    return food, reserve["id"], purchase, refund


def test_the_626_reserve_case(c, setup):
    food, reserve_id, purchase, refund = _case(c, setup)
    cash_before = c.budgets.owned_spending(*parse_month("2026-11")).get(food)
    assert _plan(c, food, "2026-11") == Decimal("-200")  # unlinked: today's behaviour
    assert _reserve(c, reserve_id)["spent"] == Decimal("1000")

    c.refunds.link(refund.id, purchase.id)
    row = _reserve(c, reserve_id)
    assert (row["spent"], row["effective_allocated"]) == (Decimal("800"), Decimal("200"))
    assert _plan(c, food, "2026-11") == Decimal("0")
    assert _plan(c, food, "2026-10") == Decimal("0")  # the purchase month is untouched
    assert c.budgets.owned_spending(*parse_month("2026-11")).get(food) == cash_before  # cash unchanged
    assert c.budgets.estimate_spending(*parse_month("2026-11")).get(food, 0) == 0
    assert c.budgets.estimate_spending(*parse_month("2026-10")).get(food, 0) == 0
    assert c.reserves.breakdown_at("2026-11-11") is None or all(
        r["effective_allocated"] == 0 for r in c.reserves.breakdown_at("2026-11-11") if r["id"] == reserve_id)
    assert [r["amount"] for r in c.reserves.returns_for_reserve(reserve_id)] == [Decimal("200")]
    assert [(r["name"], r["amount"]) for r in c.reserves.returned_by_refund(refund.id)] == [("New fridge", Decimal("200"))]

    c.refunds.unlink(refund.id)  # everything back where it was
    assert _reserve(c, reserve_id)["spent"] == Decimal("1000")
    assert _plan(c, food, "2026-11") == Decimal("-200")


def test_only_the_reserve_funded_part_goes_back(c, setup):
    food, reserve_id, purchase, refund = _case(c, setup, refund_amount="500", funded="300")
    c.refunds.link(refund.id, purchase.id)
    assert _reserve(c, reserve_id)["spent"] == Decimal("0")  # the reserve's 300 came back in full
    assert _plan(c, food, "2026-11") == Decimal("-200")  # the other 200 lowers the month as before
    assert _plan(c, food, "2026-10") == Decimal("700")


def test_a_refund_in_the_purchase_month_and_the_room_it_frees(c, setup):
    accounts, _ = setup
    food, reserve_id, purchase, refund = _case(c, setup, refund_date="2026-10-20")
    c.refunds.link(refund.id, purchase.id)
    assert _plan(c, food, "2026-10") == Decimal("0")
    # The 200 back can pay for something else from the same reserve, and a restore check agrees.
    other = c.transactions.record_outflow("2026-11-02", accounts["cib"].id, "200", food)
    c.reserves.set_expense_link(reserve_id, other.id, "200")
    c.transactions.check_reserve_links([other.id, purchase.id])
    assert _reserve(c, reserve_id)["effective_allocated"] == Decimal("0")


def test_voiding_the_refund_puts_the_money_back_in_use(c, setup):
    food, reserve_id, purchase, refund = _case(c, setup)
    c.refunds.link(refund.id, purchase.id)
    c.transactions.void(refund.id)
    assert _reserve(c, reserve_id)["spent"] == Decimal("1000")
    assert _plan(c, food, "2026-11") == Decimal("0")


def _client(c, phone=False):
    app = create_app(c)
    if phone:
        inner = app

        async def phone_app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize("phone", [False, True])
def test_the_screens_say_where_the_200_went(c, setup, phone):
    _, _, purchase, refund = _case(c, setup)
    c.refunds.link(refund.id, purchase.id)
    client = _client(c, phone)
    page = visible_text(client.get(f"/transactions/{refund.id}").text)
    assert "Went back to New fridge" in page and "200.00" in page
    page = visible_text(client.get("/plan/reserves").text)
    assert "Refund 200 back" in page and "200 still set aside" in page
    assert client.post("/settings/locale", data={"locale": "ar"}).status_code == 303
    assert "رجع لـNew fridge" in visible_text(client.get(f"/transactions/{refund.id}").text)
