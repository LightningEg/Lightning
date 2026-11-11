"""r30 / r34: one door to add an investment, gold in one step, honest chart rows, held-for-others actions."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


@pytest.fixture
def client(c):
    return TestClient(create_app(c), follow_redirects=False)


def test_two_gold_bars_of_one_karat_both_save(c):
    first = c.assets.create_investment("BTC 10g bar", "GOLD", karat="24")
    second = c.assets.create_investment("Second 24K bar (5g)", "GOLD", karat="24")
    third = c.assets.create_investment("Second 24K bar (5g)", "GOLD", karat="24")
    assert first.code == "GLD:24K" and second.code != first.code and third.code != second.code
    assert first.purity == second.purity == third.purity == D(1)


def test_add_investment_offers_the_five_doors(client):
    html = client.get("/investments/add").text
    for door in ("Stock or fund", "Certificate", "Gold", "Property", "Something else"):
        assert door in html
    assert "/investments/add" in client.get("/investments").text


def test_trade_form_lists_only_what_can_be_chosen(client, c, setup):
    accounts, _ = setup
    c.assets.create_investment("Gold 21K", "GOLD", karat="21")
    html = client.get(f"/investments/new?kind=buy&account={accounts['thndr'].id}").text
    assert "GLD:21K" in html or "Gold 21K" in html
    assert "CIB CD" not in html.split('name="cash_account_id"')[1].split("</select>")[0]


def test_add_gold_creates_item_and_purchase_in_one_post(client, c, setup):
    accounts, _ = setup
    form = {"kind": "Bar", "name": "10g bar", "weight": "10", "karat": "24", "pieces": "2", "total": "40000",
            "workmanship": "2000", "date": "2026-09-05", "paid_from": str(accounts["cib"].id), "notes": ""}
    r = client.post("/investments/gold/new", data=form)
    assert r.status_code in (302, 303), r.text[:500]
    gold = next(a for a in c.accounts.list() if a.account_type.value == "PHYSICAL_ASSET")
    items = c.physical_items.for_account(gold.id)
    assert [i["name"] for i in items] == ["10g bar"]
    assert c.investments.portfolio("2026-12-31", gold.id).positions[0].quantity == 2
    # a 22K piece saves without the person picking a reference
    r = client.post("/investments/gold/new", data=form | {"name": "Ring", "kind": "Jewelry", "karat": "22",
                                                          "paid_from": "owned", "total": "0", "workmanship": "0"})
    assert r.status_code in (302, 303), r.text[:500]


def test_held_for_others_rows_have_actions(client, c, setup):
    accounts, _ = setup
    c.counterparties.ensure_person("Mom")
    c.money_from_others.record("2026-09-12", "Mom", accounts["cib"].id, D("10000"))
    html = client.get("/money-from-others").text
    assert "Give back" in html and "Receive more" in html and "Hold money for someone" in html
    assert "How to record ownership" not in html


def test_bars_and_coins_are_rows_valued_by_the_karat_price(client, c, setup):
    """IV-12L: a bar held by the gram follows the dated karat price (not what was paid) and shows whole EGP."""
    from lightning.accounts.domain import AccountType
    gold = c.accounts.create("Gold", AccountType.PHYSICAL_ASSET, opening_date="2026-01-01")
    bar = c.assets.create_investment("10g bar", "GOLD", karat="24")
    c.assets.set_price(bar.id, "2026-09-01", "5314")
    c.investments.add_holding(gold.id, bar.id, "10", "62000", "2026-09-05")
    position = next(p for p in c.investments.portfolio("2026-12-31", gold.id).open if p.asset_id == bar.id)
    assert position.value == D("53140") and position.price_source != "COST"
    html = client.get(f"/accounts/{gold.id}").text
    assert "10g bar" in html and "53,140" in html and "53,140.00" not in html and "24K price, 1 Sep" in html
