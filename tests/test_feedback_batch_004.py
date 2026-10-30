"""Feedback batch 004 (tickets 96-112, 2026-10-16): one test per ticket. Retire when the batch is old."""
from pathlib import Path

from fastapi.testclient import TestClient

from lightning.core.dates import today
from lightning.ui.web import create_app

ROOT = Path(__file__).parents[1]


def test_undo_is_a_header_icon_with_a_shortcut():
    """Ticket 101: Undo is an icon in the page header (Ctrl+Z); no text button spills into the page."""
    base = (ROOT / "lightning/ui/templates/base.html").read_text(encoding="utf-8")
    top = base[base.index('<div class="topbar">'):base.index('{% include "partials/section_tabs.html" %}')]
    assert 'partials/history.html' in top and base.count('partials/history.html') == 1
    history = (ROOT / "lightning/ui/templates/partials/history.html").read_text(encoding="utf-8")
    assert 'icon-btn history-btn' in history and "Ctrl+Z" in history and "btn small" not in history
    js = (ROOT / "lightning/ui/static/app.js").read_text(encoding="utf-8")
    assert 'data-history="${operation}"' in js and 'e.shiftKey ? "redo" : "undo"' in js


def test_a_crash_shows_a_calm_page_not_the_server_text(c, setup):
    """Ticket 108: an unexpected failure and an unknown address each get an app page with a way forward."""
    app = create_app(c)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internals")

    client = TestClient(app, raise_server_exceptions=False)
    crashed = client.get("/boom")
    assert crashed.status_code == 500
    assert "Something went wrong" in crashed.text and "secret internals" not in crashed.text
    assert "Internal Server Error" not in crashed.text and 'href="/"' in crashed.text
    missing = client.get("/no-such-page")
    assert missing.status_code == 404 and "Back to the dashboard" in missing.text


def test_shares_show_their_ticker_and_funds_are_not_an_exchange(c, setup):
    """Tickets 104, 110: the holdings table names a share by its ticker; By market keeps funds apart from EGX."""
    from lightning.investments.domain import Position
    from lightning.investments.views import regroup

    share = Position(1, "Broker", 1, "STK:COMI", "Commercial International Bank", "Stocks", "Equity", "share",
                     1, 1, 0, 0, None, None, "", None)
    fund = Position(1, "Broker", 2, "FND:AZ-GOLD", "Azimut Gold Fund", "Funds › Gold", "Gold", "unit",
                    1, 1, 0, 0, None, None, "", None)
    assert share.short_name == "COMI" and fund.short_name == "Azimut Gold Fund"

    class Asset:
        def __init__(self, code):
            self.code, self.mic, self.currency = code, "XCAI", "EGP"

    from decimal import Decimal
    rows = [{"h": share, "value": Decimal(10), "cost": Decimal(1), "asset_id": 1},
            {"h": fund, "value": Decimal(5), "cost": Decimal(1), "asset_id": 2}]
    groups = regroup("market", [{"name": "Stocks", "rows": rows}], Decimal(15), accounts={}, base="EGP",
                     assets={1: Asset("STK:COMI"), 2: Asset("FND:AZ-GOLD")})
    assert {g["name"] for g in groups} == {"EGX", "Funds"}


def test_overview_cards_read_visually(c, setup, monkeypatch):
    """Tickets 97, 99, 100: overspending says so in rose, net cash flow draws money in against out, and the
    months of net cash flow are one continuous grid with the year as a hint at the start of each row."""
    accounts, cats = setup
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    c.transactions.record_inflow("2026-09-01", accounts["cib"].id, "10000", cats["EXP.WORK.SALARY"].id, "Employer")
    c.transactions.record_outflow("2026-09-05", accounts["cib"].id, "12000", cats["EXP.PERSONAL.FOOD"].id, "Carrefour")
    page = TestClient(create_app(c)).get("/?period=month&month=2026-09").text
    assert "Spent over money in" in page and "2,000 more went out than the 10,000 that came in" in page
    assert 'class="flow-bar is-in"' in page and 'class="flow-bar is-out"' in page
    css = (ROOT / "lightning/ui/static/style.css").read_text(encoding="utf-8")
    assert "repeat(12, minmax(0, 1fr))" in css and ".mcal-months .cal-month { display:grid; grid-template-columns:44px" in css


def test_a_chart_names_the_year_once_under_the_first_month_and_each_january():
    """Ticket 98: month axes read as month numbers, the year small beneath the first month and every January."""
    charts = (ROOT / "lightning/ui/templates/partials/charts.html").read_text(encoding="utf-8")
    assert 'class="chart-year"' in charts and "lab.text[5:] == '01'" in charts


def test_a_budget_that_pushes_safe_to_spend_below_zero_points_to_the_budget(c, setup):
    """Ticket 102: when the budget left to spend alone makes Safe to spend negative, Cash planning says so and links
    to the budget instead of blaming promised payments."""
    from decimal import Decimal
    accounts, cats = setup
    c.budgets.set_budget(cats["EXP.PERSONAL.FOOD"].id, "2026-12", "900000")
    assert c.forecaster.forecast(today()).safe_to_spend < Decimal(0)
    page = TestClient(create_app(c)).get("/plan").text
    assert "Adjust your budget" in page and 'href="/budget"' in page


def test_answering_the_bulk_edit_question_is_not_leaving_the_row():
    """Ticket 96: 'Change N selected rows?' opens over the row being edited; clicking its buttons must not count as
    leaving the row (that re-submitted the edit and stacked a second question, so mass editing never applied)."""
    js = (ROOT / "lightning/ui/static/app.js").read_text(encoding="utf-8")
    leaving = js[js.index('document.addEventListener("pointerdown"'):]
    leaving = leaving[:leaving.index("}, true);")]
    assert 'event.target.closest("dialog") || document.querySelector("dialog[open]")' in leaving


def test_a_foreign_account_register_reads_in_its_own_currency(c, setup):
    """Ticket 106: the register of a USD account shows Amount and Balance in USD, the pound value as the small line."""
    from lightning.database.currencies import CurrencyRegistry
    accounts, cats = setup
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "48.20")
    usd = c.account_flows.open_account("Dollar savings", "BANK", "2026-09-01", "200", currency="USD",
                                       opening_balance_date="2026-09-01")
    c.transactions.record_inflow("2026-09-05", usd.id, "50", cats["EXP.WORK.SALARY"].id, "gift")
    page = TestClient(create_app(c)).get(f"/accounts/{usd.id}").text
    assert "Amount (USD)" in page and "≈ +2,410.00 EGP" in page and "Balance (USD)" in page and 'register-balance-cell">250<' in page
    assert "Amount (EGP)" in TestClient(create_app(c)).get(f"/accounts/{accounts['cib'].id}").text
