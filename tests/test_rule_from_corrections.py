"""NF-3AZ3: filing the same counterparty the same way twice offers a rule with its past matches; the user picks the
scope, sees before and after, and can undo."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _txn(c, accounts, cat, day, party, amount="100"):
    return c.transactions.record_outflow(day, accounts["cib"].id, amount, cat, counterparty=party)


def _file(client, txn_id, category_id, back="/transactions"):
    return client.post(f"/transactions/{txn_id}/category",
                       data={"category_id": str(category_id), "return_to": back}, follow_redirects=False)


def test_the_second_same_correction_offers_a_rule_with_its_past_rows(c, setup):
    accounts, cats = setup
    food, fun = cats["EXP.PERSONAL.FOOD"].id, cats["EXP.PERSONAL.FOOD"].id
    transport = next(cat for cat in c.categories.pickable() if cat.code.startswith("EXP.PERSONAL.TRANSPORT") and not cat.is_system).id
    rows = [_txn(c, accounts, food, f"2026-10-0{i}", "Uber") for i in range(1, 6)]
    client = TestClient(create_app(c))
    first = _file(client, rows[0].id, transport)
    assert first.headers["location"].startswith("/transactions")          # one correction: no offer yet
    second = _file(client, rows[1].id, transport)
    assert second.headers["location"].startswith("/rules/offer?")
    page = client.get(second.headers["location"])
    assert "You filed Uber under" in page.text and "These 3 past entries and future matches" in page.text
    assert "→" in page.text                                                # before and after
    assert c.rules.list() == []                                            # looking saves nothing
    count = c.db.scalar("SELECT count(*) FROM transactions")
    done = client.post("/rules/offer", data={"counterparty": "Uber", "category_id": str(transport), "scope": "past",
                                             "token": c.rules.suggestion("Uber")["token"], "decision": "yes",
                                             "return_to": "/transactions"}, follow_redirects=False)
    assert done.headers["location"].startswith("/rules?undo=")
    assert len(c.rules.list()) == 1 and c.db.scalar("SELECT count(*) FROM transactions") == count
    cats_now = {c.transactions.get(r.id).lines[0].category_id for r in rows[2:]}
    assert cats_now == {transport}
    token = done.headers["location"].split("undo=")[1].split("&")[0]
    client.post("/rules/undo", data={"token": token})
    assert {c.transactions.get(r.id).lines[0].category_id for r in rows[2:]} == {food}


def test_future_only_leaves_the_past_alone_and_not_now_resets(c, setup):
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"].id
    transport = next(cat for cat in c.categories.pickable() if cat.code.startswith("EXP.PERSONAL.TRANSPORT") and not cat.is_system).id
    rows = [_txn(c, accounts, food, f"2026-10-0{i}", "Careem") for i in range(1, 5)]
    for row in rows[:2]:
        c.rules.record_correction("Careem", food, transport)
    offer = c.rules.suggestion("Careem")
    assert offer and len(offer["past"]) == 4
    c.rules.save({"counterparty_op": "is", "counterparty": "Careem", "category_id": str(transport)})
    assert len(c.rules.list()) == 1 and {c.transactions.get(r.id).lines[0].category_id for r in rows} == {food}
    assert c.rules.suggestion("Careem") is None                            # a rule now decides it


def test_a_changed_offer_is_refused_and_not_now_forgets_the_count(c, setup):
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"].id
    transport = next(cat for cat in c.categories.pickable() if cat.code.startswith("EXP.PERSONAL.TRANSPORT") and not cat.is_system).id
    _txn(c, accounts, food, "2026-10-01", "Swvl")
    for _ in range(2):
        c.rules.record_correction("Swvl", food, transport)
    stale = c.rules.suggestion("Swvl")["token"]
    _txn(c, accounts, food, "2026-10-02", "Swvl")                           # the past changed since the offer
    assert c.rules.suggestion("Swvl")["token"] != stale
    page = TestClient(create_app(c)).post("/rules/offer", data={
        "counterparty": "Swvl", "category_id": str(transport), "scope": "past", "token": stale, "decision": "yes"},
        follow_redirects=False)
    assert "changed" in page.headers["location"] and c.rules.list() == []
    TestClient(create_app(c)).post("/rules/offer", data={"counterparty": "Swvl", "category_id": str(transport),
                                                         "decision": "no"})
    assert c.rules.suggestion("Swvl") is None
