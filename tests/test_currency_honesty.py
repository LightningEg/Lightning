"""Audit 2026-10-15, brokerage report phase 0: a figure in another currency says so, and foreign money counts
foreign investments too."""
from datetime import date
from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.core.ledger import Effect, PostingLine
from lightning.core.refs import DocType
from lightning.database.currencies import CurrencyRegistry
from lightning.ui.web import create_app


def _dollar_etf(c, accounts):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    broker = c.account_flows.open_account("US broker", "BROKERAGE", "2026-09-01", "0", currency="USD",
                                          opening_balance_date="2026-09-01")
    c.transactions.record_conversion("2026-09-02", accounts["cib"].id, broker.id, "40000", "800")
    asset = c.assets.create_investment("US index ETF", "FUND.EQUITY", "VTIX", mic="XNAS")
    cash = c.assets.cash_asset("USD")
    c.transactions.post(DocType.BUY, "2026-09-03", [
        PostingLine.cash(broker.id, cash.id, D("-500"), Effect.INTERNAL, fx_rate=D("50")),
        PostingLine.units(broker.id, asset.id, D("10"), D("500"), Effect.INTERNAL, D("50"), fx_rate=D("50"))])
    c.assets.set_price(asset.id, "2026-09-30", "60")
    c.fx.save("USD", "2026-09-30", "52")
    return broker, asset


def test_foreign_money_counts_foreign_investments(c, setup):
    accounts, _ = setup
    _dollar_etf(c, accounts)
    assert c.position.foreign_holdings("2026-09-30", "EGP") == {"USD": (D("31200.000000"), False)}
    page = TestClient(create_app(c)).get("/accounts/currencies?period=custom&date_from=2026-09-01&date_to=2026-09-30").text
    # 300 USD cash at 52 = 15,600 and the ETF 31,200: 46,800 in all
    assert "46,800" in page and "Cash 15,600 · investments 31,200" in page


def test_holdings_table_leaves_foreign_price_details_on_the_holding_page(c, setup):
    accounts, _ = setup
    _dollar_etf(c, accounts)
    page = TestClient(create_app(c)).get("/investments?period=custom&date_from=2026-09-01&date_to=2026-09-30").text
    row = page[page.index('class="holding-link" href="/investments/holding/'):].split('</tr>', 1)[0]
    assert '25,000' in row and '31,200' in row and '+6,200' in row
    assert '<small' not in row and '50.00' not in row and '60.00' not in row
    # Native price and average cost remain labeled on the linked holding page (next test).


def test_holding_page_shows_what_was_paid_in_its_own_currency(c, setup):
    accounts, _ = setup
    broker, asset = _dollar_etf(c, accounts)
    page = TestClient(create_app(c)).get(f"/investments/holding/{asset.id}?account={broker.id}&date=2026-09-30").text
    assert "Price 60.00 USD" in page and "Average cost 50.00 USD" in page
    assert "50.00 <small>USD</small>" in page  # the trade's price per unit


def test_a_dollar_account_header_shows_dollars_then_pounds(c, setup):
    accounts, _ = setup
    broker, asset = _dollar_etf(c, accounts)
    c.fx.save("USD", "2026-12-31", "50")
    c.assets.set_price(asset.id, "2026-12-31", "60")
    page = TestClient(create_app(c)).get(f"/accounts/{broker.id}").text
    # 300 USD cash + 10 × 60 = 900 USD, at 50 = 45,000 EGP
    assert "900.00 <small>USD</small>" in page and "In EGP" in page and "≈ 45,000" in page


def test_a_market_you_hold_something_on_is_followed_and_cannot_be_dropped(c, setup):
    from lightning.workflows.market_prices import followed_packs, held_packs
    accounts, _ = setup
    c.settings.set("market_packs", "none")
    _dollar_etf(c, accounts)
    assert held_packs(c) == ["fx", "us"]
    assert followed_packs(c) == ["fx", "us"]
    client = TestClient(create_app(c))
    client.post("/investments/prices/markets", data={"pack": ["egx"]})
    assert followed_packs(c) == ["egx", "fx", "us"]
    page = client.get("/investments/prices/markets").text
    assert page.count("You hold something here") == 2


def test_three_decimal_currencies_and_exchanges_without_a_rate_source(c):
    from lightning.market.iso import RATED_CURRENCIES, offered_venues
    from lightning.market.sources.cbe import CURRENCY_NAMES
    CurrencyRegistry(c.db).register("KWD")
    assert c.assets.cash_asset("KWD").quantity_decimals == 3
    assert c.assets.cash_asset("EGP").quantity_decimals == 2
    assert RATED_CURRENCIES == set(CURRENCY_NAMES)  # keep the gate in step with the rate source
    venues = offered_venues("EGP")
    assert "XKUW" in venues and "XNAS" in venues and "XCAI" in venues and "XICE" not in venues
    page = TestClient(create_app(c)).get("/investments/assets/new").text
    assert ">Nasdaq</option>" in page and "XNAS</option>" not in page


def test_a_listing_can_trade_in_another_currency_than_its_exchange(c):
    london_usd = c.assets.create_investment("S&P 500 UCITS (USD line)", "FUND.EQUITY", "CSPX", mic="XLON", currency="usd")
    assert (london_usd.mic, london_usd.currency) == ("XLON", "USD")
    assert c.assets.create_investment("Vodafone", "STOCK", "VOD", mic="XLON").currency == "GBP"
    dollar_fund = c.assets.create_investment("Bank dollar fund", "FUND.MONEY_MARKET", "USDMM", currency="USD")
    assert dollar_fund.currency == "USD" and dollar_fund.mic is None
    import pytest
    from lightning.core.errors import ValidationError
    with pytest.raises(ValidationError):
        c.assets.create_investment("Iceland share", "STOCK", "ICE1", currency="ISK")
