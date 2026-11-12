"""BT-12AD: the payday proposal's four lines are disjoint and add up to Cash available to assign.

Mohab's year on 2026-10-21 had Bills protected 15,740 inside its spending line as well (35,018 + 98,183 was 15,740
more than the 117,461 it shared out). Owner, 2026-11-10: Cash available to assign is stated before those bills and
Bills protected is one of its parts; the second line is named "To your plan", not the registry's Everyday spending."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def _sums(c, day):
    plan = c.funding.preview(day)
    pr = plan["proposal"]
    assert pr["bills"] + pr["to_plan"] + pr["reserves"] + pr["unassigned"] == pr["available_before"] == plan["available"]
    assert plan["available"] == plan["cash"] - plan["reserved"] - plan["funded"]
    return plan, pr


@pytest.fixture
def mohab(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-21")
    load_mohab_2026(c)
    return c


def test_the_sample_years_lines_add_up_with_bills_inside(mohab):
    plan, pr = _sums(mohab, date(2026, 10, 21))
    assert pr["bills"] > 0                       # the case that double-counted: a bill due outside the envelopes
    assert pr["available_before"] == plan["ready"] + pr["bills"]


def test_the_demo_household_adds_up(c, monkeypatch):
    from lightning.demo import build_demo
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-09")
    build_demo(c)
    _sums(c, date(2026, 11, 9))


def test_the_page_shows_the_lines_under_their_own_names(mohab):
    with TestClient(create_app(mohab)) as client:
        page = client.get("/payday").text
    plan, pr = _sums(mohab, date(2026, 10, 21))
    proposal = page[page.index('id="payday-proposal"'):]
    proposal = proposal[:proposal.index("</section>")]
    assert "To your plan" in proposal and "Everyday spending" not in proposal
    # IV-12Q1: the cash to share out is the page's Lead, the proposal beside it; the four parts are its bar.
    lead = page[page.index('lead-card'):page.index('id="payday-proposal"')]
    assert f"{pr['available_before']:,.0f}" in lead
    assert all(f"{v:,.0f}" in proposal for v in (pr["bills"], pr["to_plan"], pr["reserves"], pr["unassigned"]))


def test_reserves_get_their_monthly_need_not_all_free_cash(mohab):
    """IV-12Q1 (r32 U1): the proposal sent 60,420 of 67,018 free cash to the emergency fund. A reserve now gets what it
    needs this month (Emergency fund top-up, a dated goal's monthly share), in whole pounds; the rest stays unassigned."""
    plan, pr = _sums(mohab, date(2026, 10, 21))
    fund = mohab.health.emergency_fund(date(2026, 10, 21))
    emergency = next(r for r in plan["reserves"] if r["name"] == "Emergency Fund")
    assert 0 < emergency["suggested"] <= fund.top_up < emergency["gap"]
    assert all(r["suggested"] <= r["monthly"] and r["suggested"] == r["suggested"].to_integral() for r in plan["reserves"])
    assert all(r["suggested"] == r["suggested"].to_integral() for r in plan["rows"])
    assert pr["unassigned"] > 0
