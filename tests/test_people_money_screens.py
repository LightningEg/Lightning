"""NF-12G6 (#529): Lend, Paid back and Forgive on the person's page (PC).

Lend 5,000, they pay back 3,000, forgive 2,000: the page reads 5,000, then 2,000, then nothing owed. Each form calls
PeopleMoneyService inside a settled save and comes back to the page with a flash; a refused amount is a flash too.
The Arabic page has no English."""
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from tests.screens import visible_text


def _client(c, locale="en"):
    client = TestClient(create_app(c), follow_redirects=False)
    if locale != "en":
        assert client.post("/settings/locale", data={"locale": locale}).status_code == 303
    return client


def _person(c):
    return c.counterparties.create("Karim")


def test_lend_repay_and_forgive_through_the_page(c, setup):
    accounts, _ = setup
    karim = _person(c)
    client = _client(c)
    page = visible_text(client.get(f"/counterparties/{karim}").text)
    assert "Between you" in page and "Nothing between you now" in page and "Lend" in page
    assert "Forgive" not in page  # nothing owed: nothing to forgive or pay back

    sent = client.post(f"/counterparties/{karim}/lend", data={"day": "2026-12-01", "account_id": str(accounts["cib"].id),
                                                              "amount": "5000"})
    assert sent.status_code == 303 and sent.headers["location"].startswith(f"/counterparties/{karim}")
    assert c.people_money.balance(karim) == Decimal("5000")
    page = visible_text(client.get(f"/counterparties/{karim}").text)
    assert "Owed to you" in page and "5,000" in page and "They paid back" in page and "Forgive" in page

    client.post(f"/counterparties/{karim}/repay", data={"day": "2026-12-10", "account_id": str(accounts["cib"].id),
                                                        "amount": "3000"})
    assert c.people_money.balance(karim) == Decimal("2000")
    assert "2,000" in visible_text(client.get(f"/counterparties/{karim}").text)

    food = c.categories.get_by_code("EXP.PERSONAL.GIFTS").id
    client.post(f"/counterparties/{karim}/forgive", data={"day": "2026-12-20", "amount": "2000",
                                                          "category_id": str(food)})
    assert c.people_money.balance(karim) == Decimal("0")
    page = visible_text(client.get(f"/counterparties/{karim}").text)
    assert "Nothing between you now" in page and "Forgive" not in page


def test_a_refused_amount_comes_back_as_a_message(c, setup):
    accounts, _ = setup
    karim = _person(c)
    client = _client(c)
    client.post(f"/counterparties/{karim}/lend", data={"day": "2026-12-01", "account_id": str(accounts["cib"].id),
                                                       "amount": "1000"})
    refused = client.post(f"/counterparties/{karim}/repay", data={"day": "2026-12-02",
                                                                  "account_id": str(accounts["cib"].id), "amount": "1500"})
    assert refused.status_code == 303 and c.people_money.balance(karim) == Decimal("1000")
    page = visible_text(client.get(refused.headers["location"]).text)
    assert "is more than that" in page
    assert client.post(f"/counterparties/{karim}/lend", data={"day": "2026-12-01", "account_id": "",
                                                              "amount": "10"}).status_code == 303
    assert c.people_money.balance(karim) == Decimal("1000")


def test_the_arabic_page_uses_the_owners_words(c, setup):
    accounts, _ = setup
    karim = _person(c)
    c.people_money.lend("2026-12-01", karim, accounts["cib"].id, "5000")
    page = visible_text(_client(c, "ar").get(f"/counterparties/{karim}").text)
    assert "ليك عند الناس" in page and "سلّف" in page and "رجّع" in page and "سامح" in page
