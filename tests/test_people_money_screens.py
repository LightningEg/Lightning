"""NF-12G6 (#529): Lend, Paid back and Forgive on the person's page (PC).

Lend 5,000, they pay back 3,000, forgive 2,000: the page reads 5,000, then 2,000, then nothing owed. Each form calls
PeopleMoneyService inside a settled save and comes back to the page with a flash; a refused amount is a flash too.
The Arabic page has no English."""
from decimal import Decimal
import pytest

from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from tests.screens import Screen, visible_text
from tests.test_journal_finance import devices  # noqa: F401
from tests.test_journal_screens import screens  # noqa: F401


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


@pytest.mark.parametrize("action", ["lend", "repay", "forgive"])
def test_resending_the_same_people_form_posts_once(c, setup, action):
    accounts, _ = setup
    account_id = accounts["cib"].id
    karim = _person(c)
    if action != "lend":
        c.people_money.lend("2026-12-01", karim, account_id, "5000")
    client = _client(c)
    path = f"/counterparties/{karim}/{action}"
    form = next(form for form in Screen(client.get(f"/counterparties/{karim}")).forms if form.action == path)
    payload = form.fields | {"day": "2026-12-02", "amount": "1000", "account_id": str(account_id),
                             "category_id": str(c.categories.get_by_code("EXP.PERSONAL.GIFTS").id)}
    before = c.db.scalar("SELECT COUNT(*) FROM transactions")
    first = client.post(path, data=payload)
    second = client.post(path, data=payload)
    assert first.status_code == second.status_code == 303
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before + 1
    assert c.people_money.balance(karim) == (1000 if action == "lend" else 4000)
    changed = client.post(path, data=payload | {"amount": "2000"})
    assert changed.status_code == 303
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before + 1
    fresh = next(form for form in Screen(client.get(f"/counterparties/{karim}")).forms if form.action == path)
    assert fresh.fields["submission"] != form.fields["submission"]
    assert client.post(path, data=payload | {"submission": fresh.fields["submission"]}).status_code == 303
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before + 2


def test_resending_a_lend_form_stages_one_transaction(screens):
    from tests.test_journal_area_plans import account, same

    (hd, pc), (home, replica) = screens
    assert home.post("/counterparties", data={"name": "Ahmed", "counterparty_action": "create",
                                              "kind": "PERSON"}).status_code == 303
    pc.sync_with(hd.home)
    person = pc.c.counterparties.resolve("Ahmed")["id"]
    path = f"/counterparties/{person}/lend"
    form = next(form for form in Screen(replica.get(f"/counterparties/{person}")).forms if form.action == path)
    payload = form.fields | {"day": "2026-09-05", "amount": "400", "account_id": str(account(pc, "Bank").id)}
    for _ in range(2):
        assert replica.post(path, data=payload, headers={"referer": f"http://testserver/counterparties/{person}"}).status_code == 303
    assert len(pc.pending_commands()) == 1
    pc.sync_with(hd.home)
    assert pc.c.people_money.balance(person) == 400
    same(hd, pc)
