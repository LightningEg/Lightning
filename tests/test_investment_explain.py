"""NF-3AZ9: an investment result explains what changed: its parts add to the Result, each links to its rows, a missing or
old price stays visible, and nothing reads as advice."""
from __future__ import annotations

from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.investments.report import explain_period, investment_period
from lightning.ui.web import create_app


def _world(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-31")
    accounts, _ = setup
    thndr = accounts["thndr"]
    c.transactions.record_transfer("2026-12-01", accounts["cib"].id, thndr.id, "20000")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    entry = {"price_basis": "total", "fees": "", "fees_included": "1", "instrument_key": "catalog:COMI", "units": "100"}
    client.post(f"/accounts/{thndr.id}/investment-entry", data={**entry, "date": "2026-12-02", "total": "7000", "trade_action": "buy"})
    client.post(f"/accounts/{thndr.id}/investment-entry", data={**entry, "date": "2026-12-20", "total": "8000", "trade_action": "sell"})
    return client


def test_the_parts_add_up_to_the_result_and_name_their_rows(c, setup, monkeypatch):
    client = _world(c, setup, monkeypatch)
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-12-01", "2026-12-31")
    explained = explain_period(report, "2026-12-01", "2026-12-31")
    assert explained["result"] is not None and explained["total"] == explained["result"]
    by_key = {p["key"]: p for p in explained["parts"]}
    assert by_key["sales"]["amount"] == D(1000) and by_key["sales"]["href"].endswith("kind=sales")
    assert explained["new_money"] >= 0 and explained["money_href"].endswith("kind=flows")
    page = client.get("/investments?period=month&month=2026-12").text
    assert "What changed" in page and "Gain from sales" in page and "It is not advice on what to buy or sell" in page
    assert "kind=sales" in page


def test_a_missing_price_makes_the_total_unavailable_and_is_listed(c, setup, monkeypatch):
    _world(c, setup, monkeypatch)
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-12-01", "2026-12-31")
    report = dict(report, unrealized_change=None, result=None, missing=[{"asset": "COMI", "reason": "Missing confirmed market price"}])
    explained = explain_period(report, "2026-12-01", "2026-12-31")
    assert explained["total"] is None and explained["missing"][0]["asset"] == "COMI"


def test_an_old_price_is_listed_as_stale(c, setup, monkeypatch):
    _world(c, setup, monkeypatch)
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-12-01", "2026-12-31")
    report["holdings"] = [{"account": "Thndr", "asset": "COMI", "account_id": 1, "asset_id": 1, "units": D(10), "cost": D(100),
                           "value": D(120), "realized": D(0), "unrealized": D(20), "price_date": "2026-10-01",
                           "price_source": "MARKET"}]
    explained = explain_period(report, "2026-12-01", "2026-12-31")
    assert explained["stale"] == [{"name": "COMI", "price_date": "2026-10-01"}]


def test_on_the_demo_profile_the_parts_still_add_to_the_result(tmp_path, monkeypatch):
    from lightning.bootstrap import build
    from lightning.demo import build_demo
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-05")
    c = build(tmp_path / "explain.db")
    build_demo(c)
    for start in ("2026-01-01", "2026-10-01"):
        report = investment_period(c.db, c.accounts, c.assets, c.reporting, start, "2026-11-05")
        explained = explain_period(report, start, "2026-11-05")
        if explained["result"] is not None:
            assert explained["total"] == explained["result"], start


def test_a_month_where_nothing_changed_is_one_line(c, setup, monkeypatch):
    """IV-12Z4: holdings that did not move, and no money in or out, read as one line, not five rows of 0."""
    accounts, _ = setup
    thndr = accounts["thndr"]
    monkeypatch.setenv("LIGHTNING_TODAY", "2027-01-31")
    c.transactions.record_transfer("2026-12-01", accounts["cib"].id, thndr.id, "20000")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    entry = {"price_basis": "total", "fees": "", "fees_included": "1", "instrument_key": "catalog:COMI", "units": "100"}
    client.post(f"/accounts/{thndr.id}/investment-entry", data={**entry, "date": "2026-12-02", "total": "7000", "trade_action": "buy"})
    page = client.get("/investments?period=month&month=2027-01").text
    assert "Nothing changed in your holdings this month." in page
    assert 'id="what-changed-h"' not in page and "Money and value by class" not in page
