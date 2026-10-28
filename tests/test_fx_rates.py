"""One exchange-rate lookup for every caller (lightning/fx.py): direct, inverse, cross through the pound, the
source order MANUAL > TRADE > MARKET > ONLINE, the 10-day "as of" and the 45-day "missing" rule, and the two
ways rates arrive by themselves: the followed fx price file and the live fetch."""
import sys
from datetime import date, datetime, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from lightning.database.currencies import CurrencyRegistry
from lightning.fx import MISSING_DAYS, STALE_DAYS, rate_for, save_rate
from lightning.market.bundle import Close, Instrument, MarketFile, write
from lightning.market.packs import MarketSet, write_index
from lightning.workflows import live_prices
from lightning.workflows.market_prices import MarketPrices

sys.path.insert(0, str(Path(__file__).parent))
from test_live_prices import Sources  # noqa: E402  (the same network stand-in)


def rate(c, base, quote, day):
    return rate_for(c.db, base, quote, day)


def test_direct_inverse_and_cross_rates(c):
    save_rate(c.db, "2026-09-20", "USD", "EGP", D("50"), "MANUAL")
    save_rate(c.db, "2026-09-20", "EUR", "EGP", D("55"), "MANUAL")
    assert rate(c, "USD", "EGP", "2026-09-25").rate == D("50")
    inverse = rate(c, "EGP", "USD", "2026-09-25")
    assert (inverse.rate, inverse.kind) == (D("0.020000"), "inverse")
    cross = rate(c, "EUR", "USD", "2026-09-25")  # 55 / 50, through the pound; never stored
    assert (cross.rate, cross.kind) == (D("1.100000"), "cross")
    assert rate(c, "USD", "EUR", "2026-09-25").rate == D("0.909091")
    assert rate(c, "USD", "USD", "2026-09-25").rate == 1
    assert c.db.scalar("SELECT COUNT(*) FROM fx_rates") == 2
    assert rate(c, "USD", "GBP", "2026-09-25") is None  # no pound rate for GBP: no cross


def test_a_rate_is_never_read_from_the_future(c):
    save_rate(c.db, "2026-09-20", "USD", "EGP", D("50"), "MANUAL")
    assert rate(c, "USD", "EGP", "2026-09-19") is None


def test_rate_lookup_at_start_of_calendar(c):
    assert rate(c, "USD", "EGP", "0001-01-01") is None
    save_rate(c.db, "0001-01-01", "USD", "EGP", D("50"), "MANUAL")
    assert rate(c, "USD", "EGP", "0001-02-15").rate == D("50")
    assert rate(c, "USD", "EGP", "0001-02-16") is None


def test_old_rates_are_shown_as_of_then_missing(c):
    save_rate(c.db, "2026-08-01", "USD", "EGP", D("50"), "MANUAL")
    assert rate(c, "USD", "EGP", "2026-08-01").as_of is None
    at_limit = rate(c, "USD", "EGP", "2026-08-11")
    assert (at_limit.age_days, at_limit.as_of) == (STALE_DAYS, None)
    stale = rate(c, "USD", "EGP", "2026-08-12")
    assert (stale.stale, stale.as_of, stale.rate) == (True, "2026-08-01", D("50"))
    assert rate(c, "USD", "EGP", "2026-09-15") is not None  # 45 days
    assert rate(c, "USD", "EGP", "2026-09-16") is None       # 46 days: missing
    assert MISSING_DAYS == 45


def test_a_cross_rate_is_as_old_as_its_older_leg(c):
    save_rate(c.db, "2026-09-01", "USD", "EGP", D("50"), "MANUAL")
    save_rate(c.db, "2026-09-28", "EUR", "EGP", D("55"), "MANUAL")
    cross = rate(c, "EUR", "USD", "2026-09-30")
    assert (cross.date, cross.stale) == ("2026-09-01", True)


def test_source_order_on_a_day_and_newer_day_first(c):
    for source, value in (("ONLINE", "50.1"), ("MARKET", "50.2"), ("TRADE", "50.3")):
        save_rate(c.db, "2026-09-10", "USD", "EGP", D(value), source)
    assert rate(c, "USD", "EGP", "2026-09-10").source == "TRADE"
    save_rate(c.db, "2026-09-10", "USD", "EGP", D("50.4"), "MANUAL")
    top = rate(c, "USD", "EGP", "2026-09-10")
    assert (top.source, top.rate) == ("MANUAL", D("50.4"))
    save_rate(c.db, "2026-09-12", "USD", "EGP", D("50.9"), "ONLINE")  # a newer day beats an older manual rate
    assert rate(c, "USD", "EGP", "2026-09-13").rate == D("50.9")
    assert rate(c, "USD", "EGP", "2026-09-11").rate == D("50.4")


def test_posting_uses_the_same_lookup_and_names_the_limit(c, setup):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-07-01", "50")
    with pytest.raises(Exception, match="within 45 days"):
        c.account_flows.open_account("Dollars", "BANK", "2026-09-30", "10", currency="USD",
                                     opening_balance_date="2026-09-30")
    c.fx.save("USD", "2026-09-25", "51")
    c.account_flows.open_account("Dollars", "BANK", "2026-09-30", "10", currency="USD",
                                 opening_balance_date="2026-09-30")
    assert c.reporting.foreign_currency_accounts("2026-09-30")[0]["value"] == D("510")


def test_a_stale_rate_still_values_but_says_as_of(c):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    c.account_flows.open_account("Dollars", "BANK", "2026-09-01", "10", currency="USD",
                                 opening_balance_date="2026-09-01")
    group = c.reporting.foreign_currency_accounts("2026-09-30")[0]
    assert group["value"] == D("500") and group["rate_as_of"] == "2026-09-01"
    c.fx.save("USD", "2026-09-29", "52")
    assert c.reporting.foreign_currency_accounts("2026-09-30")[0]["rate_as_of"] is None


def test_a_missing_rate_goes_to_needs_you_with_the_way_to_fix_it(c):
    from lightning.workflows.review import ReviewInbox
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-08-01", "50")
    c.account_flows.open_account("Dollars", "BANK", "2026-08-01", "10", currency="USD",
                                 opening_balance_date="2026-08-01")
    assert not [i for i in ReviewInbox(c).items(date(2026, 9, 10)) if i["label"] == "Missing valuation"]
    item = next(i for i in ReviewInbox(c).items(date(2026, 9, 30)) if i["label"] == "Missing valuation")
    assert "rate within 45 days" in item["detail"] and "tab=rates" in item["href"]


# ------------------------------------------------------------------ rates that arrive by themselves
def _fx_file(tmp_path, closes, pair="USD/EGP"):
    root = tmp_path / "pub"
    root.mkdir()
    item = Instrument(pair, "US dollar", "CURRENCY", "EGP", unit="USD")
    write(root / "fx", [item], [Close(d, pair, D(v)) for d, v in closes], "2026-09-30T14:00:00Z", pack="fx")
    write_index(root, "2026-09-30T14:00:00Z")
    return MarketSet({"fx": MarketFile.open(root / "fx")})


def test_the_fx_price_file_fills_rates_as_market_source(c, setup, tmp_path):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "48")
    c.account_flows.open_account("Dollars", "BANK", "2026-09-01", "10", currency="USD",
                                 opening_balance_date="2026-09-01")
    market = _fx_file(tmp_path, [("2026-09-01", "48.1"), ("2026-09-29", "48.6"), ("2026-09-30", "48.7")])
    MarketPrices(c.assets, c.reporting).fill(market, date(2026, 9, 30))
    rows = c.db.all("SELECT date,base,quote,source FROM fx_rates WHERE source=? ORDER BY date", ("MARKET",))
    assert rows and all((r["base"], r["quote"], r["source"]) == ("USD", "EGP", "MARKET") for r in rows)
    assert {r["date"] for r in rows} == {"2026-09-01", "2026-09-30"}  # the day dollars moved, and the latest
    assert rate(c, "USD", "EGP", "2026-09-30").rate == D("48.7")
    c.fx.save("USD", "2026-09-30", "49")  # a typed rate wins the same day
    assert rate(c, "USD", "EGP", "2026-09-30").rate == D("49")


def test_the_fx_file_ignores_currencies_the_profile_does_not_use(c, setup, tmp_path):
    market = _fx_file(tmp_path, [("2026-09-30", "48.7")])  # USD is not registered
    MarketPrices(c.assets, c.reporting).fill(market, date(2026, 9, 30))
    assert c.db.scalar("SELECT COUNT(*) FROM fx_rates") == 0


def test_live_fetch_saves_yahoo_rates_as_online_for_each_foreign_currency(c, setup, monkeypatch):
    monkeypatch.delenv(live_prices.OFFLINE_ENV, raising=False)
    monkeypatch.setattr(live_prices, "_job", None)
    CurrencyRegistry(c.db).register("USD")
    CurrencyRegistry(c.db).register("EUR")
    c.fx.save("USD", "2026-09-01", "50")
    c.fx.save("EUR", "2026-09-01", "55")
    c.account_flows.open_account("Dollars", "BANK", "2026-09-01", "10", currency="USD",
                                 opening_balance_date="2026-09-01")
    c.account_flows.open_account("Euros", "BANK", "2026-09-01", "10", currency="EUR",
                                 opening_balance_date="2026-09-01")
    sources = Sources(history={"EGP%3DX": {"2026-09-28": 48.2, "2026-09-29": 48.4},
                               "EUREGP%3DX": {"2026-09-28": 53.0, "2026-09-29": 53.5}})
    report = live_prices.fetch_now(c, date(2026, 9, 30), sources, datetime(2026, 9, 30, 9, tzinfo=timezone.utc))
    assert report.rates >= 2
    usd, eur = rate(c, "USD", "EGP", "2026-09-30"), rate(c, "EUR", "EGP", "2026-09-30")
    assert (usd.rate, usd.source, usd.date) == (D("48.4"), "ONLINE", "2026-09-29")
    assert (eur.rate, eur.source) == (D("53.5"), "ONLINE")
    assert rate(c, "EUR", "USD", "2026-09-30").kind == "cross"
