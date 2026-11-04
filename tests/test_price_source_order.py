"""NF-5F: when one day holds several prices, one written order decides (reporting/price_sources.py)."""
from decimal import Decimal as D

import pytest

from lightning.reporting.valuation import SOURCE_RANK


@pytest.fixture
def stock(c, setup):
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-01-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    return c, accounts["thndr"].id, comi


def price_on(c, comi, day):
    return c.reporting.valuer.value(comi, D(1), day).price


def test_the_order_is_written_once():
    assert SOURCE_RANK[:5] == ("MANUAL", "REEVALUATION_MANUAL", "TRADE", "MARKET", "ONLINE") and SOURCE_RANK[-1] == "COST"


def test_a_manual_price_beats_the_packs_price_that_day(stock):
    c, _, comi = stock
    c.assets.set_price(comi.id, "2026-03-01", "50", source="MARKET")
    c.assets.set_price(comi.id, "2026-03-01", "55")
    assert price_on(c, comi, "2026-03-01") == D("55")
    c.assets.remove_price(comi.id, "2026-03-01")  # without it the pack's price stands
    assert price_on(c, comi, "2026-03-01") == D("50")


def test_the_packs_later_price_beats_an_older_manual_one(stock):
    c, _, comi = stock
    c.assets.set_price(comi.id, "2026-03-01", "55")
    c.assets.set_price(comi.id, "2026-03-05", "50", source="MARKET")
    assert price_on(c, comi, "2026-03-06") == D("50")
    assert price_on(c, comi, "2026-03-03") == D("55")


def test_a_trade_price_counts_for_its_own_day_and_beats_the_pack_but_not_a_manual_price(stock):
    c, broker, comi = stock
    c.investments.buy("2026-03-10", broker, comi.id, "10", "60")
    c.assets.set_price(comi.id, "2026-03-10", "50", source="MARKET")
    assert price_on(c, comi, "2026-03-10") == D("60")  # the trade of that day
    c.assets.set_price(comi.id, "2026-03-10", "58")
    assert price_on(c, comi, "2026-03-10") == D("58")  # a price you typed still wins
    assert price_on(c, comi, "2026-03-09") != D("60")  # the trade does not reach back before its day


def test_online_quotes_rank_below_the_pack(stock):
    c, _, comi = stock
    c.assets.set_price(comi.id, "2026-03-01", "49", source="ONLINE")
    c.assets.set_price(comi.id, "2026-03-01", "50", source="MARKET")
    assert price_on(c, comi, "2026-03-01") == D("50")
