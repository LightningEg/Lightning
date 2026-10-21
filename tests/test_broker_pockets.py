"""One row per broker, a cash pocket per currency (brokerage design 2026-10-15, owner decisions 2026-10-16):
a listing in another currency is held in that currency's pocket; convert, then buy; no margin."""
from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import LightningError
from lightning.database.currencies import CurrencyRegistry
from lightning.ui.web import create_app


def _broker_with_cash(c, accounts, egp="60000"):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    c.fx.save("USD", "2026-11-30", "50")
    c.fx.save("USD", "2026-12-31", "50")
    c.transactions.record_inflow("2026-09-01", accounts["cib"].id, "20000", c.categories.get_by_code("EXP.WORK.SALARY").id)
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, accounts["thndr"].id, egp)
    etf = c.assets.create_investment("US index ETF", "FUND.EQUITY", "VTIX", mic="XNAS")
    c.assets.set_price(etf.id, "2026-12-31", "110")
    return accounts["thndr"], etf


def test_convert_then_buy_puts_the_units_in_a_usd_pocket_of_the_same_broker(c, setup):
    accounts, _ = setup
    thndr, etf = _broker_with_cash(c, accounts)
    c.investments.buy_converting("2026-09-03", thndr.id, etf.id, "10", "1000", "51000")
    pocket = c.accounts.pocket_for(thndr, "USD")
    assert pocket.parent_id == thndr.id and pocket.name == "THNDR · USD" and pocket.currency == "USD"
    assert c.accounts.pockets(thndr.id) == [pocket]
    assert c.reporting.account_balance(thndr.id, "2026-09-03") == D("9000")      # 60,000 − 51,000 EGP
    assert c.reporting.account_balance(pocket.id, "2026-09-03") == D("0")        # 1,000 USD converted, all spent
    assert c.investments.holding(pocket.id, etf.id, "2026-09-03") == D("10")
    assert c.investments.holding(thndr.id, etf.id, "2026-09-03") == D("0")
    # Bought at 51 EGP per dollar: the cost in pounds is what left THNDR.
    p = c.position.at(date(2026, 12, 31))
    row = next(h for h in p.classes for h in h.items if h.asset_id == etf.id)
    assert row.account_id == pocket.id and row.value == D("55000")             # 10 × 110 USD × 50


def test_a_sale_and_a_dividend_in_the_broker_land_in_its_pocket(c, setup):
    accounts, _ = setup
    thndr, etf = _broker_with_cash(c, accounts)
    c.investments.buy_converting("2026-09-03", thndr.id, etf.id, "10", "1000", "51000")
    c.investments.sell_total("2026-12-01", thndr.id, etf.id, "4", "440")
    c.investments.dividend("2026-12-02", thndr.id, etf.id, "5")
    pocket = c.accounts.pocket_for(thndr, "USD")
    assert c.reporting.account_balance(pocket.id, "2026-12-02") == D("445")
    assert c.investments.holding(pocket.id, etf.id, "2026-12-02") == D("6")


def test_no_margin_a_pocket_cannot_spend_what_it_does_not_hold(c, setup):
    accounts, _ = setup
    thndr, etf = _broker_with_cash(c, accounts)
    with pytest.raises(LightningError):
        c.investments.buy_total("2026-09-03", thndr.id, etf.id, "10", "1000")
    assert c.investments.holding(thndr.id, etf.id, "2026-09-03") == D("0")


def test_pockets_are_brokerage_only_and_one_per_currency(c, setup):
    accounts, _ = setup
    thndr, _ = _broker_with_cash(c, accounts)
    c.accounts.add_pocket(thndr.id, "USD")
    with pytest.raises(LightningError):
        c.accounts.add_pocket(thndr.id, "USD")
    with pytest.raises(LightningError):
        c.accounts.add_pocket(thndr.id, "ISK")
    with pytest.raises(LightningError):
        c.accounts.add_pocket(accounts["cib"].id, "USD")


def test_the_entry_form_buys_a_dollar_etf_in_an_egp_broker_by_converting(c, setup):
    accounts, _ = setup
    thndr, etf = _broker_with_cash(c, accounts)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    reply = client.post(f"/accounts/{thndr.id}/investment-entry", data={
        "date": "2026-09-03", "instrument_key": f"asset:{etf.id}", "trade_action": "buy", "units": "10",
        "total": "1000", "price_basis": "total", "fees": "", "fees_included": "1", "paid_from": "51000"},
        follow_redirects=False)
    assert reply.status_code in (302, 303), reply.text[:500]
    pocket = c.accounts.pocket_for(thndr, "USD")
    assert c.investments.holding(pocket.id, etf.id, "2026-09-03") == D("10")


def test_one_row_per_broker_in_the_sidebar_and_accounts_and_its_page_shows_each_currency(c, setup):
    accounts, _ = setup
    thndr, etf = _broker_with_cash(c, accounts)
    c.investments.buy_converting("2026-09-03", thndr.id, etf.id, "10", "1000", "51000")
    pocket = c.accounts.pocket_for(thndr, "USD")
    _, _, groups = c.reporting.sidebar(date(2026, 12, 31))
    rows = [child for g in groups for child in g.children]
    assert pocket.id not in [r.id for r in rows]
    broker_row = next(r for r in rows if r.id == thndr.id)
    assert broker_row.value == D("9000") + D("55000")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    listing = client.get("/accounts").text
    assert "THNDR · USD" not in listing and "64,000" in listing
    page = client.get(f"/accounts/{thndr.id}").text
    assert "0.00 USD" in page and "9,000.00 EGP" in page and "US index ETF" in page
    assert f"/accounts/{pocket.id}" in page
    assert "Part of THNDR" in client.get(f"/accounts/{pocket.id}").text
    reply = client.post(f"/accounts/{thndr.id}/pockets", data={"currency": "eur"}, follow_redirects=False)
    assert reply.status_code == 303 and c.accounts.pocket_for(thndr, "EUR").name == "THNDR · EUR"
