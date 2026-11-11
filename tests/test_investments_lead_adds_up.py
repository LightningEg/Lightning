"""BT-12AC: the Investments Lead's parts add up to its Portfolio value, over the same holdings as the table.

Mohab's year holds a 400,000 flat known only by its balance: it used to be in Portfolio value and left out of the
Lead's Cost and Unrealized gain (325,088 and +27,399 under 752,486). Now it is its own part, Valued by you."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from starlette.responses import HTMLResponse

from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def _context(c, monkeypatch, url="/investments"):
    from lightning.ui.routes import investments as routes
    context = {}

    def capture(request, template, **values):
        context.clear(); context.update(values)
        return HTMLResponse("ok")
    monkeypatch.setattr(routes, "render", capture)
    with TestClient(create_app(c)) as client:
        assert client.get(url).status_code == 200
    return context


def _table_totals(context):
    groups = context["holding_groups"]
    return sum((g["cost"] for g in groups), D(0)), sum((g["value"] for g in groups), D(0))


def _check(context):
    lead, parts = context["lead"], context["lead_parts"]
    assert parts.cost + parts.unrealized + parts.valued_by_you == parts.value == lead["value"]
    table_cost, table_value = _table_totals(context)
    assert parts.cost + parts.valued_by_you == table_cost        # the table's All holdings Cost
    assert parts.value == table_value
    shown = sum((p["value"] for p in (lead["visual"] or {}).get("parts", [])), D(0))
    if parts.unrealized >= 0 and lead["visual"]:
        assert shown == parts.value                              # the bar's segments are the whole figure
    return parts


def test_the_sample_years_lead_counts_the_flat_as_valued_by_you(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-21")
    load_mohab_2026(c)
    context = _context(c, monkeypatch)
    parts = _check(context)
    assert parts.valued_by_you == D("400000") and parts.value == c.position.at("2026-10-21").portfolio_value
    assert "Valued by you 400,000" in context["lead"]["line"]["text"]


@pytest.fixture
def shared(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    broker = c.account_flows.open_account("Mixed broker", "BROKERAGE", "2026-09-01", "1000")
    owner = c.counterparties.create("Saved person")
    salary = c.categories.get_by_code("EXP.WORK.SALARY").id
    c.transactions.record_inflow("2026-09-01", broker.id, "1000", salary, owner_id=owner)
    asset = c.assets.create_investment("Shared share", "STOCK", "LEADTEST")
    c.investments.buy("2026-09-02", broker.id, asset.id, "4", "10")
    c.investments.buy("2026-09-02", broker.id, asset.id, "6", "10", owner_id=owner)
    c.assets.set_price(asset.id, "2026-09-20", "15")
    return c


def test_held_for_others_units_keep_the_lead_and_the_table_in_step(shared, monkeypatch):
    parts = _check(_context(shared, monkeypatch, "/investments?period=month&month=2026-09"))
    assert (parts.cost, parts.unrealized, parts.value) == (D("40.00"), D("20.00"), D("60"))
