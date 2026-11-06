"""Offline samples for the added Muscat and Nasdaq Nordic market metadata.

The fixtures exercise the adapter shape without claiming that these TradingView boards answered live.
"""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from lightning.market.iso import VENUE_CURRENCY, VENUES, venue_currency, venue_name
from lightning.market.packs import PACKS, publishable
from lightning.market.sources import tradingview
from lightning.market.model import Quote
from tools.market.collect import _settle_keys


@pytest.fixture
def market_samples():
    """Small screener rows with the columns TradingView's adapter consumes."""
    return {
        "sweden": {"data": [{"s": "OMXSTO:ERIC_B", "d": ["ERIC_B", "Ericsson B", 74.5, "SEK", "stock", "common", "OMXSTO"]}]},
        "denmark": {"data": [{"s": "OMXCOP:NOVO_B", "d": ["NOVO_B", "Novo Nordisk B", 640.2, "DKK", "stock", "common", "OMXCOP"]}]},
        "finland": {"data": [{"s": "OMXHEX:NOKIA", "d": ["NOKIA", "Nokia Oyj", 4.127, "EUR", "stock", "common", "OMXHEX"]}]},
        "iceland": {"data": [{"s": "OMXICE:ICEAIR", "d": ["ICEAIR", "Icelandair Group", 1.42, "ISK", "stock", "common", "OMXICE"]}]},
    }


def test_pack_registry_covers_all_gcc_and_nasdaq_nordic_venues():
    gcc = {mic for board in tradingview.BOARDS["gcc"] for mic in board.venues.values()}
    europe = {mic for board in tradingview.BOARDS["europe"] for mic in board.venues.values()}

    assert gcc == set(PACKS["gcc"].venues) == {"XSAU", "XDFM", "XADS", "DSMQ", "XKUW", "XBAH"}
    # TradingView has no "oman" screener (HTTP 404 in the 2026-11-04 run): Oman waits for another source.
    assert "oman" not in {board.screener for board in tradingview.BOARDS["gcc"]}
    assert {"XLON", "XETR", "XPAR", "XAMS", "XBRU", "XLIS", "XMAD", "XMIL", "XSWX",
            "XSTO", "XCSE", "XHEL", "XICE"} <= europe
    assert set(PACKS["europe"].venues) == europe
    # TradingView terms do not authorize republishing these collected rows.
    assert PACKS["gcc"].publish is False and PACKS["europe"].publish is False
    assert "gcc" not in publishable(("gcc", "europe"))
    assert "europe" not in publishable(("gcc", "europe"))


@pytest.mark.parametrize("mic,country,currency,name", [
    ("XMUS", "OM", "OMR", "Muscat Stock Exchange"),
    ("XSTO", "SE", "SEK", "Nasdaq Stockholm"),
    ("XCSE", "DK", "DKK", "Nasdaq Copenhagen"),
    ("XHEL", "FI", "EUR", "Nasdaq Helsinki"),
    ("XICE", "IS", "ISK", "Nasdaq Iceland"),
])
def test_new_venues_have_iso_country_name_and_currency(mic, country, currency, name):
    assert VENUES[mic] == (name, country)
    assert VENUE_CURRENCY[mic] == currency
    assert venue_name(mic) == name
    assert venue_currency(mic) == currency


@pytest.mark.parametrize("pack,screener,mic,country,currency,key,close", [
    ("europe", "sweden", "XSTO", "SE", "SEK", "SE:ERIC_B", D("74.5")),
    ("europe", "denmark", "XCSE", "DK", "DKK", "DK:NOVO_B", D("640.2")),
    ("europe", "finland", "XHEL", "FI", "EUR", "FI:NOKIA", D("4.127")),
    ("europe", "iceland", "XICE", "IS", "ISK", "IS:ICEAIR", D("1.42")),
])
def test_added_board_samples_keep_key_venue_currency_and_quote_units(
        market_samples, pack, screener, mic, country, currency, key, close):
    board = next(board for board in tradingview.BOARDS[pack] if board.screener == screener)
    result = tradingview.parse(market_samples[screener], board, "2026-10-12", f"tradingview-{pack}")

    assert len(result.instruments) == len(result.quotes) == 1
    instrument, quote = result.instruments[0], result.quotes[0]
    assert (instrument.key, instrument.mic, instrument.country, instrument.currency) == (key, mic, country, currency)
    assert instrument.sources["tradingview"] == market_samples[screener]["data"][0]["s"]
    assert quote == Quote(key, "2026-10-12", close, f"tradingview-{pack}")
    instrument.check()


def test_same_country_ticker_on_two_venues_gets_a_stable_venue_key():
    board = tradingview.BOARDS["gcc"][1]
    result = tradingview.parse({"data": [
        {"s": "DFM:SHARED", "d": ["SHARED", "Shared listing", 10, "AED", "stock", "common", "DFM"]},
        {"s": "ADX:SHARED", "d": ["SHARED", "Shared listing", 10.2, "AED", "stock", "common", "ADX"]},
    ]}, board, "2026-10-12", "tradingview-gcc")

    _settle_keys(result, {})
    assert [(item.key, item.mic, item.currency) for item in result.instruments] == [
        ("AE:SHARED", "XDFM", "AED"), ("AE:SHARED-XADS", "XADS", "AED")]
    assert [(quote.key, quote.close) for quote in result.quotes] == [
        ("AE:SHARED", D("10")), ("AE:SHARED-XADS", D("10.2"))]

    later = replace(result.instruments[0], mic="XADS")
    repeat = type(result)("tradingview-gcc", [later], [Quote("AE:SHARED", "2026-10-13", D("10.4"), "tradingview-gcc")])
    _settle_keys(repeat, {"AE:SHARED": result.instruments[0]})
    assert repeat.instruments[0].key == repeat.quotes[0].key == "AE:SHARED-XADS"


def test_an_unknown_exchange_is_skipped_instead_of_given_a_neighboring_venue():
    sweden = next(board for board in tradingview.BOARDS["europe"] if board.screener == "sweden")
    result = tradingview.parse({"data": [
        {"s": "OMXNO:UNKNOWN", "d": ["UNKNOWN", "Other market", 12, "NOK", "stock", "common", "OMXNO"]},
    ]}, sweden, "2026-10-12", "tradingview-europe")

    assert result.instruments == [] and result.quotes == []


def test_new_venue_currencies_are_registered_and_can_have_manual_fx(c):
    from lightning.database.currencies import CurrencyRegistry
    from lightning.fx import rate_for

    registry = CurrencyRegistry(c.db)
    for currency in ("OMR", "SEK", "DKK", "ISK"):
        assert any(row["code"] == currency for row in registry.suggestions(currency))
        registry.register(currency)
        c.fx.save(currency, "2026-10-12", "50")
        assert rate_for(c.db, currency, "EGP", "2026-10-12").rate == D("50")


def test_london_board_asks_for_pence_listings_and_drops_foreign_lines():
    board = next(b for b in tradingview.BOARDS["europe"] if b.screener == "uk")
    assert board.currencies == ("GBX",)
    assert {"left": "currency", "operation": "in_range", "right": ["GBX"]} in tradingview.query(board, "stocks")["filter"]
    assert all(f["left"] != "currency" for f in tradingview.query(board, "etfs")["filter"])  # UCITS ETFs list in USD too
    result = tradingview.parse({"data": [
        {"s": "LSE:VOD", "d": ["VOD", "Vodafone", 72.5, "GBX", "stock", "common", "LSE"]},
        {"s": "LSE:0Q15", "d": ["0Q15", "Abbott", 110.0, "USD", "stock", "common", "LSE"]}]}, board, "2026-11-04", "t")
    assert [(i.key, i.currency) for i in result.instruments] == [("GB:VOD", "GBP")]
    assert result.quotes[0].close == D("0.725")
