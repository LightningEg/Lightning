"""NF-12AB2: one "working" shape from the services. Each headline figure's owner returns the rows that add up to it,
so the PC's "How it adds up" and the phone's sheet draw the same rows and no screen adds anything up."""
from __future__ import annotations

from datetime import date

import pytest

from lightning.core.dates import month_of


@pytest.fixture
def mohab(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    from lightning.samples import load_mohab_2026
    load_mohab_2026(c)
    return c, date(2026, 10, 20)


def test_every_working_adds_up_to_its_figure_on_the_sample_year(mohab):
    c, day = mohab
    position = c.position.at(day)
    forecast = c.forecaster.forecast(day)
    everyday = c.forecaster.everyday(month_of(day), day)
    flow = c.reporting.cash_flow(day.replace(day=1), day)
    fund = c.budgets.emergency_fund(month_of(day), None, schedule=c.schedules.view())
    workings = [position.net_worth_working, position.portfolio_working, forecast.safe_to_spend_working,
                flow.savings_rate_working, fund.working, everyday.left_working]
    for working in workings:
        assert working.rows, working.figure
        assert working.adds_up, (working.figure, working.total, working.sum, working.rows)
        assert working.home.startswith("/"), working.figure
    keys = {w.figure for w in workings}
    assert keys == {"net_worth", "portfolio_value", "safe_to_spend", "savings_rate", "emergency_fund", "left_in_plan"}
