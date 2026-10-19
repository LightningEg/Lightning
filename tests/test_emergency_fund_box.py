"""The emergency fund's "Amount set aside" box shows what the fund holds now, and saving that figure
changes nothing (review 2026-10-04: after a 6,500 repair paid from a 20,000 fund the box still said
20,000 while every other screen said 13,500)."""
from decimal import Decimal


def test_the_box_shows_the_fund_after_payments_and_saving_it_changes_nothing(c, setup, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    accounts, cats = setup
    fund = c.reserves.set_emergency_fund("20,000")
    repair = c.transactions.record_outflow("2026-10-18", accounts["cib"].id, "6500", cats["EXP.PERSONAL.FOOD"].id)
    c.reserves.set_expense_link(fund["id"], repair.id, "6500")
    client = TestClient(create_app(c))
    page = client.get("/plan/reserves").text
    assert 'name="allocated" value="13,500.00"' in page and "13,500 left of 20,000 · 6,500 used" in page and "Refill to 20,000" in page
    c.reserves.set_emergency_fund("13,500")
    emergency = next(r for r in c.reserves.list_active() if r["kind"] == "EMERGENCY")
    assert emergency["effective_allocated"] == Decimal("13500")
    c.reserves.set_emergency_fund("15,000")                 # topping it up adds to what it holds now
    emergency = next(r for r in c.reserves.list_active() if r["kind"] == "EMERGENCY")
    assert emergency["effective_allocated"] == Decimal("15000")


def test_reserve_autosave_returns_fresh_server_calculated_summaries(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    from lightning.core.money import fmt
    from lightning.core.dates import today
    reserve = c.reserves.create("Car insurance", "10000")
    before = c.position.at(today()).free_cash
    client = TestClient(create_app(c))
    response = client.post(f"/reserves/{reserve['id']}/allocate", data={"allocated": "2000"},
                           headers={"X-Requested-With": "fetch"})
    assert response.status_code == 200
    assert c.position.at(today()).free_cash == before - Decimal("2000")
    assert 'data-reserve-refresh="overview"' in response.text
    assert fmt(before - Decimal("2000"), places=0) in response.text
    assert 'src="/static/reserve-autosave.js?v=2"' in response.text
