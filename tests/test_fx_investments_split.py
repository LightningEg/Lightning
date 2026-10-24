"""A foreign holding's unrealized gain, split into the part that came from its price and the part that came from the
exchange rate (Investments report). The two always add up to the gain the screen shows."""
from decimal import Decimal as D

from lightning.core.ledger import Effect, PostingLine
from lightning.core.refs import DocType
from lightning.database.currencies import CurrencyRegistry
from lightning.investments.report import build_investment_report, foreign_gain_split


def test_the_split_adds_up_to_the_gain():
    price, fx = foreign_gain_split(D("10"), D("500"), D("25000"), D("60"), D("52"))
    assert (price, fx) == (D("5200"), D("1000"))
    assert price + fx == D("10") * D("60") * D("52") - D("25000")
    losing_price, gaining_fx = foreign_gain_split(D("10"), D("500"), D("25000"), D("45"), D("52"))
    assert (losing_price, gaining_fx) == (D("-2600"), D("1000"))        # the price fell, the dollar rose


def test_a_dollar_holding_reports_price_and_fx_apart(c, setup):
    accounts, _ = setup
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    broker = c.account_flows.open_account("US broker", "BROKERAGE", "2026-09-01", "0", currency="USD",
                                          opening_balance_date="2026-09-01")
    c.transactions.record_conversion("2026-09-02", accounts["cib"].id, broker.id, "40000", "800")
    asset = c.assets.create_investment("US index ETF", "FUND.EQUITY", "VTIX")
    c.db.execute("UPDATE financial_assets SET currency='USD' WHERE id=?", (asset.id,))
    cash = c.assets.cash_asset("USD")
    c.transactions.post(DocType.BUY, "2026-09-03", [
        PostingLine.cash(broker.id, cash.id, D("-500"), Effect.INTERNAL, fx_rate=D("50")),
        PostingLine.units(broker.id, asset.id, D("10"), D("500"), Effect.INTERNAL, D("50"), fx_rate=D("50"))])
    c.assets.set_price(asset.id, "2026-09-30", "60")
    c.fx.save("USD", "2026-09-30", "52")
    row = next(h for h in build_investment_report(c.db, c.accounts, c.assets, c.reporting,
                                                  "2026-09-01", "2026-09-30")["holdings"] if h["asset"] == "US index ETF")
    assert (row["cost"], row["value"], row["unrealized"]) == (D("25000.00"), D("31200.000000"), D("6200.000000"))
    assert (row["price_part"], row["fx_part"]) == (D("5200"), D("1000.000000"))
    assert row["price_part"] + row["fx_part"] == row["unrealized"]
    assert (row["currency"], row["cost_native"]) == ("USD", D("500"))


def test_the_investments_table_shows_one_gain_without_secondary_fx_annotations(c, setup, monkeypatch):
    """The clean holding row retains its correct total gain; the report service keeps the tested price/FX split."""
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    accounts, _ = setup
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    broker = c.account_flows.open_account("US broker", "BROKERAGE", "2026-09-01", "0", currency="USD",
                                          opening_balance_date="2026-09-01")
    c.transactions.record_conversion("2026-09-02", accounts["cib"].id, broker.id, "40000", "800")
    etf = c.assets.create_investment("Nasdaq 100 ETF", "FUND.EQUITY", "QQQT", mic="XNAS")
    assert etf.currency == "USD"
    c.investments.buy_total("2026-09-03", broker.id, etf.id, "10", "500")
    c.assets.set_price(etf.id, "2026-09-30", "60")
    c.fx.save("USD", "2026-09-30", "52")
    page = TestClient(create_app(c)).get("/investments?period=month&month=2026-09").text
    table = page[page.index('class="holding-group"'):]
    row = table[table.index("Nasdaq 100 ETF"):]
    row = row[:row.index("</tr>")]
    assert "25,000" in row and "31,200" in row and "+6,200" in row
    assert "<small" not in row and "Price part" not in row and "FX part" not in row
