"""OV-3 and OV-8 (tab-by-tab review §4): why net worth changed, and net worth in dollars and 21K gold.

The bridge's parts always add up to the change; Market moves are the investment report's gains; the units divide by
the dated rate and gold price the app already stores. Both are worked out in lightning/planning/position.py."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.database.currencies import CurrencyRegistry
from lightning.investments.report import investment_period
from lightning.planning.position import net_worth_bridge
from lightning.ui.web import create_app

D = Decimal


def test_the_bridge_adds_up_and_leaves_other_as_the_rest():
    report = {"realized": D(500), "unrealized_change": D(1500)}
    bridge = net_worth_bridge(D(10000), D(7000), report)
    assert bridge == {"net_flow": D(7000), "market_moves": D(2000), "other_changes": D(1000), "change": D(10000)}
    assert net_worth_bridge(None, D(7000), report) is None  # an unknown change has no bridge
    assert net_worth_bridge(D(1), D(0), {"realized": D(0), "unrealized_change": None}) is None  # nor a missing price


def test_a_price_rise_is_a_market_move_and_a_loan_payment_is_other(c, setup, monkeypatch):
    """Salary 20,000 in, a 2,500 loan payment out (money out, but what you owe falls by as much), and shares bought
    at 100 that end the period at 120: change = net flow + market moves + other, to the pound."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-31")
    accounts, cats = setup
    share = c.assets.create_investment("Shares", "STOCK", "SHR")
    c.assets.set_price(share.id, "2026-09-25", "100")
    c.transactions.record_inflow("2026-09-25", accounts["thndr"].id, "1000", cats["EXP.WORK.SALARY"].id)
    c.investments.buy("2026-09-26", accounts["thndr"].id, share.id, "10", "100")
    c.transactions.record_inflow("2026-10-01", accounts["cib"].id, "20000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "3000", cats["EXP.PERSONAL.FOOD"].id)
    c.assets.set_price(share.id, "2026-10-20", "120")
    first, last = date(2026, 10, 1), date(2026, 10, 31)
    change, _ = c.position.change_in_what_you_own(first, last)
    flow = c.reporting.cash_flow(first, last)
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-10-01", "2026-10-31")
    bridge = net_worth_bridge(change, flow.net, report)
    assert bridge["net_flow"] == D(17000) and bridge["market_moves"] == D(200)
    assert bridge["net_flow"] + bridge["market_moves"] + bridge["other_changes"] == change
    assert bridge["other_changes"] == 0  # nothing else moved
    page = TestClient(create_app(c)).get("/?period=month&month=2026-10").text
    assert "Market moves" in page and "+200" in page and "Other changes" in page


def test_net_worth_in_dollars_and_21k_gold_uses_the_stored_dated_prices(c, setup):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    gold = c.assets.get_asset_by_code("REF:GLD-24K")
    c.assets.set_price(gold.id, "2026-09-01", "4800")  # 21K is 4,800 × 21/24 = 4,200 a gram
    units = {u["unit"]: u for u in c.position.in_other_units(D(84000), "2026-09-30",
                                                                c.zakat.gold_price_24k("2026-09-30"))}
    assert units["US dollars"]["value"] == D(1680) and units["US dollars"]["date"] == "2026-09-01"
    assert units["grams of 21K gold"]["value"] == D(20) and units["grams of 21K gold"]["price"] == D(4200)
    assert c.position.in_other_units(D(84000), "2026-09-30", None)[-1]["unit"] == "US dollars"  # no gold price: no gold


def test_no_rate_and_no_gold_price_show_no_units(c, setup):
    assert c.position.in_other_units(D(84000), "2026-09-30", c.zakat.gold_price_24k("2026-09-30")) == []
