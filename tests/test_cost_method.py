"""NF-5B3: a brokerage account chooses average cost or oldest-first; the portfolio, the period report and the
holding journey all read it, so one sale shows one gain everywhere."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.investments.report import build_investment_report
from lightning.ui.web import create_app


@pytest.fixture
def held(c, setup):
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-01-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    thndr = accounts["thndr"].id
    c.investments.buy("2026-02-01", thndr, comi.id, "10", "100")
    c.investments.buy("2026-03-01", thndr, comi.id, "10", "200")
    c.investments.sell("2026-04-01", thndr, comi.id, "10", "250")
    return c, accounts, thndr, comi


def position(c, thndr, comi):
    return next(p for p in c.investments.portfolio("2026-12-31", thndr).positions if p.asset_id == comi.id)


def test_new_accounts_use_the_average_cost(held):
    c, _, thndr, comi = held
    assert c.accounts.get(thndr).cost_method == "average"
    p = position(c, thndr, comi)
    assert (p.cost_basis, p.realized) == (D("1500"), D("1000"))
    assert [lot.cost for lot in p.lots] == [D("1500")]


def test_oldest_first_takes_the_cost_of_the_first_purchase(held):
    c, _, thndr, comi = held
    c.accounts.set_cost_method(thndr, "fifo")
    p = position(c, thndr, comi)
    assert (p.cost_basis, p.realized) == (D("2000"), D("1500"))
    assert [(lot.opened, lot.cost) for lot in p.lots] == [("2026-03-01", D("2000"))]
    assert [(piece.lot_opened, piece.gain) for piece in p.disposals] == [("2026-02-01", D("1500"))]
    c.accounts.set_cost_method(thndr, "average")
    assert position(c, thndr, comi).realized == D("1000")  # nothing is stored: switching back restores it


@pytest.mark.parametrize("method,gain", [("average", D("1000")), ("fifo", D("1500"))])
def test_the_period_report_agrees_with_the_portfolio(held, method, gain):
    c, _, thndr, comi = held
    c.accounts.set_cost_method(thndr, method)
    report = build_investment_report(c.db, c.accounts, c.assets, c.reporting, "2026-04-01", "2026-04-30")
    assert report["realized"] == gain == position(c, thndr, comi).realized
    row = next(h for h in report["holdings"] if h["asset_id"] == comi.id)
    assert (row["cost"], row["realized"]) == (position(c, thndr, comi).cost_basis, gain)


def test_only_a_brokerage_account_has_a_cost_method(held):
    c, accounts, thndr, _ = held
    with pytest.raises(ValidationError):
        c.accounts.set_cost_method(accounts["cib"].id, "fifo")
    with pytest.raises(ValidationError):
        c.accounts.set_cost_method(thndr, "lifo")


def test_the_account_menu_switches_the_method(held):
    c, _, thndr, _ = held
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    assert "Sell the oldest purchase first" in client.get(f"/accounts/{thndr}").text
    client.post(f"/accounts/{thndr}/cost-method", data={"method": "fifo"})
    assert c.accounts.get(thndr).cost_method == "fifo"
    assert "Use the average cost for sales" in client.get(f"/accounts/{thndr}").text


def test_the_holding_page_shows_each_purchase_and_each_sold_piece(held):
    c, _, thndr, comi = held
    c.accounts.set_cost_method(thndr, "fifo")
    c.assets.set_price(comi.id, "2026-12-30", "300")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get(f"/investments/holding/{comi.id}?account={thndr}").text
    assert "Each purchase" in page and "Still held" in page and "Per year" in page
    assert "2026-03-01" in page and "2026-02-01" in page  # the open lot and the lot the sale came from
