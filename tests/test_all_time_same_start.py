"""All time starts at your first record on every tab (bug found 2026-10-04: Investments started its
All time at the oldest latest-price date of what you hold now, so its money in left out months)."""
import re


def test_all_time_money_in_is_the_same_on_investments_and_the_overview(c, setup, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-31")
    accounts, cats = setup
    for month in ("09", "10", "11", "12"):
        c.transactions.record_inflow(f"2026-{month}-01", accounts["cib"].id, "30000", cats["EXP.WORK.SALARY"].id)
    thndr = accounts["thndr"]
    c.transactions.record_transfer("2026-10-05", accounts["cib"].id, thndr.id, "10000")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    client.post(f"/accounts/{thndr.id}/investment-entry", data={
        "price_basis": "total", "fees": "", "fees_included": "1", "instrument_key": "catalog:COMI",
        "units": "100", "total": "7000", "trade_action": "buy", "date": "2026-10-06"})
    comi = next(a for a in c.assets.investments(active_only=True) if a.code.endswith("COMI"))
    c.assets.set_price(comi.id, "2026-12-15", "75")
    flat = lambda html: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    investments = flat(client.get("/investments?period=all").text)
    overview = flat(client.get("/?period=all").text)
    assert re.search(r"Money in ([\d,]+)", investments).group(1) == "120,000"
    assert re.search(r"Money in ([\d,]+)", overview).group(1) == "120,000"


def test_all_time_money_in_is_the_same_on_budget_and_the_overview(c, setup, monkeypatch):
    # Budget started its All time at the first spending, so income before it was left out.
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-31")
    accounts, cats = setup
    c.transactions.record_inflow("2026-09-02", accounts["cib"].id, "30000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_inflow("2026-10-01", accounts["cib"].id, "30000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_outflow("2026-10-10", accounts["cib"].id, "500", cats["EXP.PERSONAL.FOOD"].id)
    client = TestClient(create_app(c))
    flat = lambda html: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    budget = flat(client.get("/budget?period=all").text)
    overview = flat(client.get("/?period=all").text)
    assert re.search(r"Money in ([\d,]+)", overview).group(1) == "60,000"
    assert re.search(r"Money in ([\d,]+)", budget).group(1) == "60,000"
