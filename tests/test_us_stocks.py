"""US stocks (v1.1, package A): an investment is priced in its exchange's currency, the picker lists US stocks and
ETFs beside EGX, and live prices treat a US listing as USD."""
from __future__ import annotations

import csv

from lightning.assets import catalog
from lightning.market.iso import VENUES, VENUE_CURRENCY, is_currency, venue_currency
from lightning.workflows.live_prices import CURRENCY, instrument_key


def test_every_venue_has_a_currency_and_it_is_iso():
    assert set(VENUE_CURRENCY) == set(VENUES)
    assert all(is_currency(code) for code in VENUE_CURRENCY.values())
    assert venue_currency("XNAS") == venue_currency("XNYS") == venue_currency("ARCX") == "USD"
    assert venue_currency("XCAI") == "EGP" and venue_currency("") is None and venue_currency("ZZZZ") is None


def test_a_us_stock_is_in_dollars_and_dollars_are_registered(c):
    assert "USD" not in {row["code"] for row in c.currencies.list()}
    apple = c.assets.create_investment("Apple Inc.", "STOCK", "AAPL", mic="XNAS")
    assert (apple.currency, apple.mic, apple.country, apple.market_key) == ("USD", "XNAS", "US", "US:AAPL")
    assert "USD" in {row["code"] for row in c.currencies.list()}
    etf = c.assets.create_investment("Invesco QQQ Trust, Series 1", "FUND.EQUITY", "QQQ", mic="XNAS")
    assert etf.currency == "USD"


def test_egx_stocks_funds_and_gold_follow_their_venue(c):
    assert c.assets.create_investment("CIB", "STOCK", "COMI").currency == "EGP"
    assert c.assets.create_investment("AZ Savings", "FUND.FIXED_INCOME", "AZS").currency == c.base_currency
    assert c.assets.create_investment("Gold", "GOLD", "", karat="21").currency == c.base_currency


def test_live_prices_treat_a_us_listing_as_dollars(c):
    apple = c.assets.create_investment("Apple Inc.", "STOCK", "AAPL", mic="XNAS")
    key, pack = instrument_key(apple)
    assert (key, pack) == ("US:AAPL", "us") and CURRENCY[pack] == apple.currency


def test_a_dollar_buy_posts_its_pound_value_at_the_days_rate(c):
    from decimal import Decimal
    import pytest
    from lightning.core.errors import ValidationError

    c.currencies.register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    usd = c.account_flows.open_account("Dollar brokerage", "BROKERAGE", "2026-09-01", "2,000", currency="USD")
    pounds = c.account_flows.open_account("Pound brokerage", "BROKERAGE", "2026-09-01", "90,000")
    qqq = c.assets.create_investment("Invesco QQQ Trust", "FUND.EQUITY", "QQQ", mic="XNAS")
    txn = c.investments.buy("2026-09-02", usd.id, qqq.id, "10", "100")
    lines = c.db.all("SELECT amount_e6, fx_rate_e6, amount_base_e6 FROM ledger_entries WHERE transaction_id=? "
                     "ORDER BY id", (txn.id,))
    assert [(r["amount_e6"], r["fx_rate_e6"], r["amount_base_e6"]) for r in lines] == [
        (-1_000_000_000, 50_000_000, -50_000_000_000), (1_000_000_000, 50_000_000, 50_000_000_000)]
    assert c.reporting.account_balance(usd.id) == Decimal("1000")
    with pytest.raises(ValidationError, match="priced in USD"):
        c.investments.buy("2026-09-02", pounds.id, qqq.id, "1", "100")
    with pytest.raises(ValidationError, match="priced in USD"):
        c.investments.buy("2026-09-02", usd.id, qqq.id, "1", "100", cash_account_id=pounds.id)


def test_the_catalogue_lists_egx_and_us_without_clashes():
    rows = catalog.instruments()
    us = [row for row in rows if row["mic"] in ("XNAS", "XNYS", "ARCX")]
    assert sum(row["kind"] == "Stocks" for row in us) >= 300 and sum(row["kind"] == "ETFs" for row in us) >= 60
    assert all(row["currency"] == "USD" and row["mic"] in VENUES for row in us)
    assert any(row["ticker"] == "COMI" and row["mic"] == "XCAI" and row["currency"] == "EGP" for row in rows)
    listings = [(row["ticker"].upper(), row["mic"]) for row in rows]
    # A ticker may sit on two exchanges (EGX and Milan both list AZM): the picker names the exchange and the second
    # asset's code carries it (U9), so a listing, not a ticker, is listed once.
    assert len(listings) == len(set(listings))
    assert not {t for t, m in listings if m in ("XCAI", "")} & {t for t, m in listings if m in ("XNAS", "XNYS", "ARCX")}
    with catalog.US_CATALOGUE_FILE.open(encoding="utf-8-sig", newline="") as source:
        head = next(csv.reader(source))
    assert head == ["ticker", "name", "kind", "class_code", "source", "source_url", "catalogue_date", "mic", "currency"]


def test_the_rebuild_tool_writes_the_same_columns_from_a_screener_answer(tmp_path):
    from tools.market import us_catalogue

    class Fake:
        def post_json(self, url, payload):
            kind = payload["filter"][-1]["right"]
            rows = ([["NASDAQ:AAPL", ["AAPL", "Apple Inc.", 230, "USD", "stock", "common", "NASDAQ"]],
                     ["NYSE:COMI", ["COMI", "Clash with EGX", 10, "USD", "stock", "common", "NYSE"]]]
                    if kind != "etf" else
                    [["AMEX:GLD", ["GLD", "SPDR Gold Shares", 400, "USD", "fund", "etf", "AMEX"]]])
            return {"data": [{"s": symbol, "d": values} for symbol, values in rows]}

    out = tmp_path / "us.csv"
    assert us_catalogue.rebuild(Fake(), out, day="2026-10-13") == 2
    with out.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    assert [(r["ticker"], r["kind"], r["class_code"], r["mic"], r["currency"]) for r in rows] == [
        ("AAPL", "Stocks", "STOCK", "XNAS", "USD"), ("GLD", "ETFs", "FUND.GOLD", "ARCX", "USD")]


def test_foreign_listing_requirements_are_arabic_in_the_picker(c, monkeypatch):
    from lightning.ui.routes.register import _trade_choices
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-01")
    c.settings.set("locale", "ar")
    broker = c.account_flows.open_account("Broker", "BROKERAGE", "2026-09-01", "0")
    choice = next(r for r in _trade_choices(c, broker, []) if r["ticker"] == "QQQM")
    # A broker holds a foreign listing in its own pocket (2026-10-16): only the rate is missing.
    assert "مسعّر" in choice["note"] and "سعر صرف" in choice["note"]
    assert "Priced" not in choice["note"] and "account" not in choice["note"]
    c.currencies.register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    c.account_flows.open_account("US broker", "BROKERAGE", "2026-09-01", "0", currency="USD")
    choice = next(r for r in _trade_choices(c, broker, []) if r["ticker"] == "QQQM")
    assert "جيب" in choice["note"] and "pocket" not in choice["note"]
