"""Feedback batch 003 (retired 2026-10-15; see git history): the screen fixes, one test per ticket."""
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def test_what_you_owe_rows_open_like_free_cash(c, setup, monkeypatch):
    """Ticket 95: Bills due and Loans still to pay open to their items; the loan note is a line, not a small font."""
    accounts, _ = setup
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-10")
    c.planning.create(kind="BILL", name="Internet", amount="650", frequency="ONCE", start_date="2026-10-05")
    c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY", start_date="2026-10-01",
                      end_date="2027-01-01")
    page = TestClient(create_app(c)).get("/plan").text
    owe = page[page.index("owe-card"):]
    assert owe.count('class="overview-disclosure"') == 2
    assert "Internet" in owe and "Car loan" in owe
    assert "Loan payments that are due are counted in Loans still to pay." in owe
    assert "other than loan payments" not in owe


def test_the_csv_file_field_is_a_labelled_well(c, setup):
    """Ticket 91: the file chooser sits in a field under its label, styled by style.css (never the browser's box)."""
    accounts, _ = setup
    page = TestClient(create_app(c)).get(f"/accounts/{accounts['cib'].id}/import").text
    assert '<div class="field import-file-field"><label for="bank-csv">' in page
    css = (Path(__file__).parents[1] / "lightning/ui/static/style.css").read_text(encoding="utf-8")
    assert "input[type=file]:not(#_):not(.x_)::file-selector-button" in css


def test_a_month_shows_where_money_went_beside_the_last_six_months(c, setup):
    """Ticket 78: a month's Sankey sits beside the six months ending with it; a longer period keeps one."""
    accounts, cats = setup
    for month in ("08", "09", "10"):
        c.transactions.record_inflow(f"2026-{month}-01", accounts["cib"].id, "10000", cats["EXP.WORK.SALARY"].id)
        c.transactions.record_outflow(f"2026-{month}-05", accounts["cib"].id, "3000", cats["EXP.PERSONAL.FOOD"].id)
    client = TestClient(create_app(c))
    month = client.get("/?period=month&month=2026-10").text
    assert "overview-sankey-card is-pair" in month and "The last six months" in month
    assert "2026-08 to 2026-10" in month
    year = client.get("/?period=custom&date_from=2026-08-01&date_to=2026-10-31").text
    assert "is-pair" not in year


def test_the_overview_keeps_net_cash_flow_by_month_as_a_calendar(c, setup):
    """Tickets 79, 85, 86: months drawn like the day calendar on the Overview; the daily expenses calendar and the
    daily net cash flow are not on the Overview."""
    accounts, cats = setup
    c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "300", cats["EXP.PERSONAL.FOOD"].id)
    page = TestClient(create_app(c)).get("/?period=month&month=2026-10").text
    months = page[page.index('id="months-heading"'):]
    assert "mcal-months" in months and 'class="cal-grid mcal-grid"' in months
    assert "Total expenses" not in months and "less to more spent" not in months


def test_free_cash_no_longer_repeats_itself(c, setup):
    """Ticket 83: Free cash sits beside what you own by kind; If you sold today beside the period's net flow."""
    page = TestClient(create_app(c)).get("/").text
    cash = page[page.index("overview-cash-card"):page.index("overview-owned-card")]
    assert "How it is built" not in cash and 'id="madeof-heading"' in cash
    owned = page[page.index("overview-owned-card"):page.index('id="cashflow-analysis-heading"')]
    assert 'id="sold-heading"' in owned and 'id="flow-heading"' in owned


def test_plan_to_invest_shows_only_for_todays_position(c, setup):
    """Ticket 80: Your position follows the period; the planner works from today, so a past period hides it."""
    client = TestClient(create_app(c))
    assert "Plan to invest" in client.get("/").text
    assert "Plan to invest" not in client.get("/?period=month&month=2026-09").text


def test_the_system_group_says_what_it_holds(c, setup, monkeypatch):
    """Ticket 93: "System Categories" no longer reads "Personal" under its name; it names its active categories."""
    import re
    accounts, _ = setup
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-10")
    loans = c.categories.get_by_code("EXP.SYSTEM.LOANS")
    c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "2500", loans.id, allow_system_category=True)
    page = TestClient(create_app(c)).get("/budget?period=month&month=2026-10").text
    summary = re.search(r"<b>System Categories</b>(<small>[^<]*</small>)?", page)
    assert summary and summary.group(1) == "<small>Loan payments</small>"


def test_the_investing_rate_is_the_share_of_what_you_kept(c, setup):
    """Ticket 89: Money added ÷ Net flow, at most 100%; nothing kept means no rate."""
    from lightning.investments.report import investing_rate
    assert investing_rate(Decimal("2500"), Decimal("10000")) == Decimal("25")
    assert investing_rate(Decimal("15000"), Decimal("10000")) == Decimal("100")
    assert investing_rate(Decimal("2500"), Decimal("0")) is None
    page = TestClient(create_app(c)).get("/investments").text
    assert "part of it" not in page  # The Savings card has no second investing percentage
