"""Each app fetches its own prices (lightning/workflows/live_prices.py): month-end closes by itself the first
time it opens after a month ends, everything on Update prices; never a moving intraday price; a typed price
wins; and nothing is asked when nothing is due."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.market.model import SourceError
from lightning.ui.web import create_app
from lightning.workflows import live_prices, market_prices
from lightning.workflows.live_prices import (apply_finished, due_month_ends, failures, fetch_if_due, fetch_now,
                                             final_day, probe, probe_summary, start_if_due)


def _stamp(day: str, hour: int = 12) -> int:
    return int(datetime.fromisoformat(day).replace(hour=hour, tzinfo=timezone.utc).timestamp())


class Sources:
    """Stands in for the network: TradingView's EGX board, Mubasher's funds and Yahoo's history."""

    def __init__(self, board=None, history=None, funds=None, fund_history="", fail=()):
        self.board, self.history, self.funds, self.fund_history = board or {}, history or {}, funds or [], fund_history
        self.fail, self.asked = set(fail), []

    def _check(self, what):
        self.asked.append(what)
        if what in self.fail:
            raise SourceError(f"{what} is down")

    def post_json(self, url, payload):
        self._check("tradingview")
        return {"data": [{"s": f"EGX:{t}", "d": [t, t, close, "EGP", "stock", "common", "EGX"]}
                         for t, close in self.board.items()]}

    def get_json(self, url, params=None):
        if "mubasher" in url:
            self._check("mubasher")
            return {"rows": self.funds, "numberOfPages": 1}
        self._check("yahoo:" + url.rsplit("/", 1)[-1])
        series = self.history.get(url.rsplit("/", 1)[-1], {})
        return {"chart": {"result": [{"timestamp": [_stamp(d) for d in series],
                                      "indicators": {"quote": [{"close": list(series.values())}]}}]}}

    def get_text(self, url, params=None):
        if "banquemisr.com" in url:
            self._check("banque-misr")
            return (Path(__file__).parent / "fixtures" / "market" / "banque_misr_rates.html").read_text(encoding="utf-8")
        if "cbe.org.eg" in url:
            self._check("cbe")
            return (Path(__file__).parent / "fixtures" / "market" / "cbe_rates.html").read_text(encoding="utf-8")
        self._check("mubasher-history")
        return self.fund_history


@pytest.fixture(autouse=True)
def online(monkeypatch, tmp_path):
    monkeypatch.delenv(live_prices.OFFLINE_ENV, raising=False)
    monkeypatch.setattr(live_prices, "_job", None)
    monkeypatch.setattr(market_prices, "BUNDLED", tmp_path / "absent" / "market.zip")


@pytest.fixture
def held(c, setup):
    accounts, _ = setup
    c.transactions.record_transfer("2026-09-01", accounts["cib"].id, accounts["thndr"].id, "40000")
    made = {"cib": c.assets.create_investment("CIB", "STOCK", "COMI"),
            "azs": c.assets.create_investment("AZ Savings", "FUND.FIXED_INCOME", "AZS"),
            "apple": c.assets.create_investment("Apple", "STOCK", "AAPL", mic="XNAS"),
            "nope": c.assets.create_investment("Nope fund", "FUND.EQUITY", "NOPE")}
    # A US listing is created in USD now; this one stands for an older holding kept in pounds.
    c.db.execute("UPDATE financial_assets SET currency='EGP' WHERE id=?", (made["apple"].id,))
    c.assets.link_market(made["azs"].id, "EG:FUND:4104")
    for asset in made.values():
        c.investments.buy("2026-09-02", accounts["thndr"].id, asset.id, "10", "50")
    return made


def test_a_close_counts_only_once_it_is_final():
    thursday = datetime(2026, 12, 31, 11, tzinfo=timezone.utc)  # EGX trades Sunday to Thursday, final 13:30 UTC
    assert final_day("egx", thursday) == date(2026, 12, 30)
    assert final_day("egx", thursday.replace(hour=14)) == date(2026, 12, 31)
    assert final_day("egx", datetime(2027, 1, 2, 9, tzinfo=timezone.utc)) == date(2026, 12, 31)  # Saturday
    first = date(2026, 9, 2)
    assert due_month_ends(date(2026, 12, 31), first, thursday)[-1] == "2026-11-30"  # today's month-end not final yet
    assert due_month_ends(date(2026, 12, 31), first, thursday.replace(hour=14))[-1] == "2026-12-31"


def test_three_days_after_a_month_end_the_app_fetches_that_close(c, held):
    sources = Sources(history={"COMI.CA": {"2026-09-29": 70, "2026-10-29": 75, "2026-11-01": 76, "2026-11-02": 77,
                                           "2026-11-03": 79}},  # Nov 3 is still trading at 09:00 UTC
                      fund_history="2026-09-30,30.5\n2026-10-30,31\n2026-11-02,31.2\n")
    morning = datetime(2026, 11, 3, 9, tzinfo=timezone.utc)
    report = fetch_if_due(c, date(2026, 11, 3), sources, morning)
    assert "tradingview" not in sources.asked  # during trading hours the board's price is still moving
    october = c.reporting.value_of(held["cib"].id, D(1), "2026-10-31")
    assert (october.price, october.price_date, october.source) == (D("75"), "2026-10-29", "ONLINE")
    latest = c.reporting.value_of(held["cib"].id, D(1), "2026-11-03")
    assert (latest.price, latest.price_date) == (D("77"), "2026-11-02")  # never today's moving price
    assert c.reporting.value_of(held["azs"].id, D(1), "2026-10-31").price == D("31")
    assert report.priced == ["CIB", "AZ Savings"] and report.other_currency == ["Apple"]
    assert report.unmatched == ["Nope fund"] and not report.missing
    assert not c.reevaluations.pending_prices() or all(
        p["asset_id"] in (held["nope"].id, held["apple"].id) for p in c.reevaluations.pending_prices())
    # tried once today: opening again does not ask again, even though Nope fund still has no price
    assert fetch_if_due(c, date(2026, 11, 3), Sources(fail={"tradingview"}), morning) is None


def test_nothing_due_means_no_request(c, held):
    for asset in held.values():
        for day in ("2026-09-30", "2026-10-31", "2026-11-30"):
            c.assets.set_price(asset.id, day, "60")  # every month-end typed
    sources = Sources()
    assert fetch_if_due(c, date(2026, 12, 15), sources, datetime(2026, 12, 15, 9, tzinfo=timezone.utc)) is None
    assert sources.asked == []


def test_offline_and_read_only_never_fetch(c, held, monkeypatch):
    monkeypatch.setenv(live_prices.OFFLINE_ENV, "1")
    sources = Sources()
    assert fetch_if_due(c, date(2026, 11, 3), sources, datetime(2026, 11, 3, 9, tzinfo=timezone.utc)) is None
    assert sources.asked == []


def test_update_prices_takes_the_whole_board_and_a_typed_price_wins(c, held):
    c.assets.set_price(held["cib"].id, "2026-12-31", "99")  # typed today
    sources = Sources(board={"COMI": 101.5, "ETEL": 40},
                      history={"COMI.CA": {"2026-09-30": 70, "2026-10-29": 75, "2026-11-30": 80}},
                      funds=[{"fundId": 4104, "name": "AZ Savings", "price": 32.1, "date": "31 December 2026"}],
                      fund_history="2026-09-30,30.5\n2026-10-30,31\n2026-11-30,31.5\n")
    report = fetch_now(c, date(2026, 12, 31), sources, datetime(2026, 12, 31, 15, tzinfo=timezone.utc))
    assert sources.asked[:2] == ["tradingview", "mubasher"]  # whole boards: they learn nothing of what you hold
    today = c.reporting.value_of(held["cib"].id, D(1), "2026-12-31")
    assert (today.price, today.source) == (D("99"), "MANUAL")
    assert c.reporting.value_of(held["cib"].id, D(1), "2026-11-30").price == D("80")
    assert c.reporting.value_of(held["azs"].id, D(1), "2026-12-31").price == D("32.1")
    assert report.summary().startswith("Fetched ")


def test_a_failing_source_is_named_and_the_month_end_waits_for_you(c, held):
    sources = Sources(fail={"tradingview", "yahoo:COMI.CA", "mubasher", "mubasher-history"})
    report = fetch_now(c, date(2026, 12, 31), sources, datetime(2026, 12, 31, 15, tzinfo=timezone.utc))
    assert report.failed == ["TradingView", "Mubasher", "Yahoo Finance"] and report.saved == 0
    assert ("CIB", "2026-10-31") in report.missing
    assert "Not reachable now: TradingView, Mubasher, Yahoo Finance." in report.summary()
    assert ("CIB", "2026-10-31") in market_prices.missing_prices(c)  # Needs you: Enter prices


def test_the_update_prices_button(c, held, monkeypatch):
    called = []
    monkeypatch.setattr(live_prices, "gather", lambda work: (called.append(work.on), ({}, ["TradingView"]))[1])
    client = TestClient(create_app(c))
    page = client.get("/investments/prices")
    assert "Update prices" in page.text and "Download shared prices" in page.text
    answer = client.post("/investments/prices/online", follow_redirects=False)
    assert answer.status_code == 303 and called
    assert "Not reachable now: TradingView." in client.get(answer.headers["location"]).text


def _wait():
    job = live_prices._job
    assert job is not None and job.done.wait(5)


def test_opening_a_profile_fetches_in_the_background_and_the_next_page_saves_it(c, held):
    sources = Sources(history={"COMI.CA": {"2026-09-29": 70, "2026-10-29": 75, "2026-11-02": 77}},
                      fund_history="2026-09-30,30.5\n2026-10-30,31\n")
    assert start_if_due(c, date(2026, 11, 3), sources, datetime(2026, 11, 3, 9, tzinfo=timezone.utc))
    _wait()
    assert not c.reevaluations.has_price(held["cib"].id, "2026-10-31")  # nothing written off the database's thread
    page = TestClient(create_app(c)).get("/investments/prices").text
    assert "Month-end prices: Fetched " in page  # said once, on the next page
    assert c.reporting.value_of(held["cib"].id, D(1), "2026-10-31").price == D("75")
    assert apply_finished(c) == "" and live_prices._job is None
    assert not start_if_due(c, date(2026, 11, 3), sources)  # once a day


def test_a_background_fetch_for_a_closed_profile_is_dropped(c, held):
    assert start_if_due(c, date(2026, 11, 3), Sources(), datetime(2026, 11, 3, 9, tzinfo=timezone.utc))
    _wait()
    assert apply_finished(object.__new__(type(c))) == "" and live_prices._job is None


def test_after_two_failed_tries_the_shared_prices_are_offered(c, held):
    down = Sources(fail={"tradingview", "yahoo:COMI.CA", "mubasher", "mubasher-history"})
    client = TestClient(create_app(c))
    fetch_now(c, date(2026, 12, 31), down, datetime(2026, 12, 31, 15, tzinfo=timezone.utc))
    page = client.get("/investments/prices").text
    assert 'id="missing"' in page and "Get prices" in page and "Use shared prices" not in page
    fetch_now(c, date(2026, 12, 31), down, datetime(2026, 12, 31, 15, tzinfo=timezone.utc))
    assert failures(c) == 2
    assert "Use shared prices" in client.get("/investments/prices").text
    for asset in held.values():
        for day in ("2026-09-30", "2026-10-31", "2026-11-30", "2026-12-31"):
            c.assets.set_price(asset.id, day, "60")
    fetch_now(c, date(2026, 12, 31), down, datetime(2026, 12, 31, 15, tzinfo=timezone.utc))
    assert failures(c) == 0  # nothing missing any more


def test_testing_the_price_sources_names_the_one_that_fails(c, monkeypatch):
    results = probe(Sources(board={"COMI": 80}, history={"COMI.CA": {"2026-10-01": 80}}, fail={"mubasher"}))
    assert [(name, works) for name, works, _ in results] == [
        ("TradingView", True), ("Yahoo Finance", True), ("Mubasher", False), ("Banque Misr", True)]
    text = probe_summary(results)
    assert "TradingView: works, 1 Egyptian stock" in text and "Mubasher: not working (mubasher is down)" in text
    monkeypatch.setattr(live_prices, "probe", lambda: results)
    client = TestClient(create_app(c))
    assert "Test price sources" in client.get("/investments/prices/markets").text
    answer = client.post("/investments/prices/markets/test", follow_redirects=False)
    assert "Mubasher: not working" in client.get(answer.headers["location"]).text


def test_pages_show_the_background_fetch_and_then_what_it_did(c, held):
    gate = __import__("threading").Event()

    class Slow(Sources):
        def get_json(self, url, params=None):
            gate.wait(5)
            return super().get_json(url, params)

    sources = Slow(history={"COMI.CA": {"2026-10-29": 75}}, fund_history="2026-10-30,31\n")
    client = TestClient(create_app(c))
    assert 'data-watch=' not in client.get("/investments").text  # nothing running: no corner note
    assert start_if_due(c, date(2026, 11, 3), sources, datetime(2026, 11, 3, 9, tzinfo=timezone.utc))
    page = client.get("/investments").text
    assert 'data-watch="/investments/prices/online/status"' in page and "Fetching month-end prices…" in page
    assert client.get("/investments/prices/online/status").json() == {"running": True, "note": ""}
    gate.set()
    _wait()
    state = client.get("/investments/prices/online/status").json()
    assert state["running"] is False and state["note"].startswith("Month-end prices: Fetched ")
    assert c.reporting.value_of(held["cib"].id, D(1), "2026-10-31").price == D("75")


def test_buttons_that_wait_on_the_network_say_what_they_do(c, held):
    client = TestClient(create_app(c))
    assert 'data-busy="Fetching prices…">Update prices<' in client.get("/investments/prices").text
    assert 'data-busy="Testing sources…">Test price sources<' in client.get("/investments/prices/markets").text


def test_a_fund_without_its_number_is_found_on_mubasher_by_its_name(c, held):
    accounts = {a.name: a for a in c.accounts.list()}
    twin = c.assets.create_investment("Twin", "FUND.EQUITY", "TWN")
    c.investments.buy("2026-09-02", accounts["THNDR"].id, twin.id, "1", "50")
    rows = [{"fundId": 4104, "name": "AZ Savings", "price": 32.1, "date": "31 December 2026"},
            {"fundId": 5150, "name": "NOPE  Fund", "price": 12.5, "date": "31 December 2026"},  # case, spaces, "fund"
            {"fundId": 7001, "name": "Twin Fund", "price": 1, "date": "31 December 2026"},
            {"fundId": 7002, "name": "The Twin", "price": 2, "date": "31 December 2026"}]  # two such names: none
    sources = Sources(funds=rows, fund_history="2026-09-30,10\n2026-10-29,11\n2026-11-30,12\n")
    report = fetch_now(c, date(2026, 12, 31), sources, datetime(2026, 12, 31, 15, tzinfo=timezone.utc))
    assert sources.asked.count("mubasher") == 1  # the one list both prices and names the funds
    assert c.assets.get_asset(held["nope"].id).market_key == "EG:FUND:5150"
    assert c.reporting.value_of(held["nope"].id, D(1), "2026-12-31").price == D("12.5")
    assert c.reporting.value_of(held["nope"].id, D(1), "2026-11-30").price == D("12")  # its month-ends too
    assert c.assets.get_asset(twin.id).market_key is None
    text = report.summary()
    assert "Found on Mubasher by name: Nope fund." in text
    assert "No fund on Mubasher is named Twin; paste its Mubasher page in Edit investment." in text


def test_a_funds_mubasher_page_is_pasted_on_edit_investment(c, held):
    client = TestClient(create_app(c))
    page = client.get(f"/investments/assets/{held['azs'].id}/edit").text
    assert 'name="fund_page"' in page and 'value="4104"' in page
    assert 'name="fund_page"' not in client.get(f"/investments/assets/{held['cib'].id}/edit").text  # funds only
    form = {"name": "Nope fund", "class_code": "FUND.EQUITY", "symbol": "NOPE", "isin": "", "mic": "", "notes": "",
            "active": "1"}
    url = f"/investments/assets/{held['nope'].id}/edit"
    client.post(url, data={**form, "fund_page": "https://english.mubasher.info/countries/eg/funds/5150/"})
    assert c.assets.get_asset(held["nope"].id).market_key == "EG:FUND:5150"
    refused = client.post(url, data={**form, "fund_page": "a fund I like"})
    assert refused.status_code == 400 and "Paste the fund&#39;s page on Mubasher" in refused.text
    client.post(url, data={**form, "fund_page": ""})
    assert c.assets.get_asset(held["nope"].id).market_key is None  # matched by name again next time


def test_gold_is_priced_from_the_world_price_for_each_purity(c, setup):
    accounts, _ = setup
    home = c.account_flows.open_account("Gold at home", "PHYSICAL_ASSET", "2026-09-01", "0")
    ref = c.assets.get_asset_by_code("REF:GLD-21K")
    ring = c.physical_items.create(home.id, "Ring", "Ring", "4", 21, ref.id)
    c.investments.add_holding(home.id, ring, "1", "18,000", "2026-09-01", "Gift")
    c.transactions.record_transfer("2026-09-01", accounts["cib"].id, accounts["wallet"].id, "100")
    # an ounce of gold at 3,110.34768 dollars is 100 dollars a gram; the dollar is 50 pounds, then 48
    sources = Sources(history={"GC%3DF": {"2026-09-30": 3110.34768, "2026-10-01": 3110.34768},
                               "EGP%3DX": {"2026-09-29": 50, "2026-10-01": 48}})
    report = fetch_now(c, date(2026, 10, 2), sources, datetime(2026, 10, 2, 9, tzinfo=timezone.utc))
    month_end = c.reporting.value_of(ref.id, D(1), "2026-09-30")
    assert (month_end.price, month_end.source) == (D("4375"), "ONLINE")  # 100 × 50 × 21/24, a pound rate a day older
    assert c.reporting.value_of(ref.id, D(1), "2026-10-01").price == D("4200")  # 100 × 48 × 21/24
    assert c.reporting.value_of(ring, D(1), "2026-10-01").value == D("16800")  # 4 grams
    assert "Gold is an estimate from the world price" in report.summary()


def test_a_fund_matches_by_its_words_not_their_order_and_the_nearest_names_are_offered():
    """An Egyptian equity fund written "Misr Bank Equity Fund" is Mubasher's "Equity Fund Misr Bank"; a USD issue is not the
    pound fund; and a fund with no exact name is offered the nearest names, never linked by guess."""
    from types import SimpleNamespace as NS
    from lightning.workflows.live_prices import Plan, Want, fund_name, link_funds
    assert fund_name("Misr Bank Equity Fund") == fund_name("The Equity Fund, Misr Bank")
    assert fund_name("Beltone Equity Fund") != fund_name("Beltone Equity Fund USD")
    listing = [NS(key="EG:FUND:1", name="Equity Fund Misr Bank"), NS(key="EG:FUND:2", name="Beltone Equity Fund USD"),
               NS(key="EG:FUND:3", name="Beltone Equity Opportunity Fund")]
    work = Plan("2026-10-30", unlinked=[Want(1, "Misr Bank Equity Fund", "", "eg-funds"),
                                        Want(2, "Beltone Equity Fund", "", "eg-funds")])
    matched = link_funds(work, listing)
    assert [w.asset_id for w in matched] == [1] and work.linked == {1: "EG:FUND:1"}
    assert 2 not in work.linked and "Beltone Equity Opportunity Fund" in work.closest[2]
