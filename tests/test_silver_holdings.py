"""NF-9C1: silver held by the gram and priced by hand."""
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.ui.web import create_app

D = Decimal


def test_silver_is_an_investment_kind_held_in_grams(c, setup):
    accounts, _ = setup
    assert "SILVER" in [k.code for k in c.assets.investment_classes()]
    silver = c.assets.create_investment("Silver bars", "SILVER", "BARS")
    assert silver.code == "SLV:BARS" and silver.unit == "gram" and silver.price_source.value == "MANUAL"
    assert c.assets.get_class_by_code("SILVER").name == "Silver"


def test_a_silver_holding_is_valued_at_the_price_you_type(c, setup):
    accounts, _ = setup
    silver = c.assets.create_investment("Silver bars", "SILVER", "BARS")
    c.transactions.record_transfer("2026-01-02", accounts["cib"].id, accounts["thndr"].id, "20000")
    c.investments.buy_total("2026-01-05", accounts["thndr"].id, silver.id, "500", "15000")
    c.assets.set_price(silver.id, "2026-06-30", "36")
    position = next(p for p in c.investments.portfolio("2026-06-30").positions if p.asset_id == silver.id)
    assert position.quantity == D("500") and position.value == D("18000") and position.price == D("36")
    assert position.cost_basis == D("15000")
    client = TestClient(create_app(c))
    page = client.get(f"/investments/holding/{silver.id}?date=2026-06-30")
    assert page.status_code == 200 and "Silver bars" in page.text


def test_the_new_investment_form_offers_silver(c):
    page = TestClient(create_app(c)).get("/investments/assets/new").text
    assert '<option value="SILVER"' in page
