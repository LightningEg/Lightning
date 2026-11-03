"""The emergency fund averages income over the months that had income, and period returns keep holdings
sold out inside the period."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _client(c):
    return TestClient(create_app(c), base_url="http://127.0.0.1")


def test_emergency_fund_uses_average_monthly_income_over_months_with_income(c, setup, monkeypatch):
    c.budgets.set_emergency_basis("income")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-15")
    accounts, cats = setup
    client = _client(c)
    for day in ("2026-10-01", "2026-11-01"):
        client.post(f"/accounts/{accounts['cib'].id}/register", data={
            "date": day, "counterparty": "Employer", "counterparty_choice": "create",
            "category": "Work › Salary", "amount": "30000"})
    c.reserves.set_emergency_fund("15000")
    page = client.get("/reserves").text
    assert "30,000" in page and "2 months with income" in page
    assert "0.5 months" in page  # 15,000 of 30,000 average monthly income, not 15,000 of 10,000
    assert c.budgets.income_average("2026-12", schedule=c.schedules.view()).amount == 30000  # the same figure the budget uses


def test_period_returns_keep_holdings_sold_out_in_the_period(c):
    client = _client(c)
    f = c.account_flows
    thndr = f.open_account("THNDR", "BROKERAGE", "2026-09-01", "20000")
    entry = {"price_basis": "total", "fees": "", "fees_included": "1"}
    client.post(f"/accounts/{thndr.id}/investment-entry", data={**entry, "date": "2026-09-10",
                "instrument_key": "catalog:COMI", "units": "100", "total": "7000", "trade_action": "buy"})
    comi = c.assets.get_asset_by_code("STK:COMI")
    client.post(f"/accounts/{thndr.id}/investment-entry", data={**entry, "date": "2026-09-20",
                "instrument_key": f"asset:{comi.id}", "units": "100", "total": "8000", "trade_action": "sell"})
    # The Overview's one-line Investments row was removed (feedback 100); the period's result is on Investments.
    returns = client.get("/investments?period=month&month=2026-09").text
    assert "+1,000" in returns

