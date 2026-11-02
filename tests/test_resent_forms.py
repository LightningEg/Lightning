"""BT-2AD: the same form sent twice (a retry, a reload that re-posts) saves once, on the five forms that did not
carry a one-time `submission` token. A fresh form is a new action; the same token with other values is refused."""
import secrets

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _count(c, sql, *args):
    return c.db.scalar(sql, args)


@pytest.fixture
def client(c):
    with TestClient(create_app(c), base_url="http://127.0.0.1") as http:
        yield http


def _twice(client, path, data):
    token = secrets.token_hex(16)
    return [client.post(path, data=data | {"submission": token}, follow_redirects=False) for _ in range(2)], token


def test_an_investment_entry_saves_once(c, setup, client):
    thndr = setup[0]["thndr"]
    c.transactions.record_transfer("2026-10-05", setup[0]["cib"].id, thndr.id, "10000")
    data = {"price_basis": "total", "fees": "", "fees_included": "1", "instrument_key": "catalog:COMI",
            "units": "100", "total": "7000", "trade_action": "buy", "date": "2026-10-06"}
    replies, _ = _twice(client, f"/accounts/{thndr.id}/investment-entry", data)
    assert [r.status_code for r in replies] == [303, 303]
    assert _count(c, "SELECT COUNT(*) FROM transactions WHERE type='BUY' AND status='POSTED'") == 1


def test_the_investment_page_form_saves_once(c, setup, client):
    thndr = setup[0]["thndr"]
    c.transactions.record_transfer("2026-10-05", setup[0]["cib"].id, thndr.id, "10000")
    assert 'name="submission"' in client.get(f"/accounts/{thndr.id}").text           # the inline entry form
    assert 'name="submission"' in client.get(f"/investments/new?kind=buy&account={thndr.id}").text


def test_a_gold_trade_saves_once(c, client):
    physical = c.account_flows.open_account("Gold at home", "PHYSICAL_ASSET", "2026-01-01", "0")
    cash = c.account_flows.open_account("Bank", "BANK", "2026-01-01", "10000")
    reference = c.assets.get_asset_by_code("GLD:18K")
    c.assets.set_price(reference.id, "2026-09-01", "1000")
    item = c.physical_items.create(physical.id, "Gold ring", "Ring", "4.2", 18, reference.id, "")
    data = {"action": "buy", "date": "2026-09-01", "quantity": "1", "total": "4200", "fees": "0",
            "cash_account_id": str(cash.id)}
    replies, _ = _twice(client, f"/accounts/{physical.id}/items/{item}/trade", data)
    assert [r.status_code for r in replies] == [303, 303]
    assert _count(c, "SELECT COUNT(*) FROM transactions WHERE type='BUY' AND status='POSTED'") == 1
    assert c.reporting.account_balance(cash.id, "2026-09-01") == 5800


def test_an_ownership_change_saves_once(c, setup, client):
    bank = setup[0]["cib"]
    person = {"id": c.counterparties.create("Mona", kind="PERSON")}
    assert 'name="submission"' in client.get(f"/accounts/{bank.id}/ownership/new").text
    data = {"mode": "assign", "date": "2026-09-02", "amount": "500", "from_owner_id": "", "to_owner_id": str(person["id"])}
    replies, token = _twice(client, f"/accounts/{bank.id}/ownership/new", data)
    assert [r.status_code for r in replies] == [303, 303]
    assert replies[0].headers["location"] == replies[1].headers["location"]   # the second answers with the first save
    changed = client.post(f"/accounts/{bank.id}/ownership/new", data=data | {"amount": "900", "submission": token},
                          follow_redirects=False)
    assert changed.status_code == 400                                            # same form, other values: refused


def test_an_instalment_purchase_saves_once(c, setup, client):
    bank = setup[0]["cib"]
    assert 'name="submission"' in client.get("/plan/purchases/new").text
    data = {"intent": "save", "name": "Washing machine", "price": "12000", "fee": "0", "months": "6",
            "first_date": "2026-10-01", "account_id": str(bank.id)}
    before = _count(c, "SELECT COUNT(*) FROM planned_items")
    replies, _ = _twice(client, "/plan/purchases/new", data)
    assert [r.status_code for r in replies] == [303, 303]
    assert _count(c, "SELECT COUNT(*) FROM planned_items") == before + 1


def test_money_held_for_others_saves_once(c, setup, client):
    bank = setup[0]["cib"]
    c.counterparties.create("Mona", kind="PERSON")
    data = {"owner": "Mona", "account_id": str(bank.id), "amount": "1000", "date": "2026-09-02"}
    replies, _ = _twice(client, "/money-from-others", data)
    assert [r.status_code for r in replies] == [303, 303]
    assert _count(c, "SELECT COUNT(*) FROM transactions WHERE type<>'OPN' AND status='POSTED'") == 1
