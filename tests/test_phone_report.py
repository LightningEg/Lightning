"""The phone's period report (behind Money): the change in what you own, money in, out and kept, the savings rate and
what investing did, for this month, last month, this year and all time. Home is always today; this is where a period lives."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.phone.screens import report as screen
from lightning.ui.web import create_app

DAY = date(2026, 10, 12)


@pytest.fixture
def mohab(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-12")
    load_mohab_2026(c)
    return c


def test_a_month_agrees_with_the_services_it_reads(mohab):
    r = screen.build(mohab, DAY, "month")
    flow = mohab.reporting.cash_flow(date(2026, 10, 1), DAY)
    change, _ = mohab.position.change_in_what_you_own(date(2026, 10, 1), DAY)
    assert (r.money_in, r.money_out, r.net) == (flow.inflows, flow.outflows, flow.net) and r.change == change
    assert r.label == "2026-10" and r.start == "2026-10-01" and r.end == "2026-10-12"


def test_last_month_is_the_whole_month_before_and_a_year_runs_from_january(mohab):
    last = screen.build(mohab, DAY, "last")
    assert (last.start, last.end) == ("2026-09-01", "2026-09-30")
    ytd = screen.build(mohab, DAY, "ytd")
    assert ytd.start == "2026-01-01" and ytd.end == "2026-10-12"
    assert screen.build(mohab, DAY, "all").label == "All time"


def test_an_unknown_period_falls_back_to_this_month_and_the_page_renders(mohab):
    assert screen.build(mohab, DAY, "garbage").key == "month"
    app = create_app(mohab)
    mount_phone(app)
    client = TestClient(app)
    page = client.get("/money/report?period=ytd")
    assert page.status_code == 200 and "Change in what you own" in page.text and ".00" not in page.text.split("<main", 1)[1]
    assert 'href="/money/report"' in client.get("/money").text
