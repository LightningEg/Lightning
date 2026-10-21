"""5H: the portfolio reconciliation explains the exchange-rate move of investment (brokerage) cash,
so Mohab's sample, with its dollar brokerage, shows no unresolved difference."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app

D = Decimal


@pytest.fixture
def sample(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    load_mohab_2026(c)
    return c


def test_the_sample_year_to_date_has_no_unresolved_reconciliation_difference(sample):
    page = TestClient(create_app(sample), base_url="http://127.0.0.1").get("/investments?period=ytd").text
    assert "Portfolio reconciliation differs" not in page


def test_the_dollar_cash_revaluation_is_its_own_figure_and_the_difference_is_zero(sample):
    from lightning.investments.report import investment_period, reconcile_portfolio
    report = investment_period(sample.db, sample.accounts, sample.assets, sample.reporting, "2026-01-01", "2026-10-04")
    recon = reconcile_portfolio(sample.investments, sample.accounts, sample.reporting, report, "2026-01-01", "2026-10-04")
    assert recon["recon_cash_revaluation"] == D("1393.75")   # Jan 600, Feb 500, then 58.75 ... 35.25 (5H investigation)
    assert abs(recon["recon_difference"]) < D("0.01")
