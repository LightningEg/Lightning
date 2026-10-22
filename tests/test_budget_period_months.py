"""Planned and Spent cover the same months (owner screenshot 2026-10-03: Food 505 planned against
50,732 spent, because months before the first plan counted their spending but nothing planned)."""
import re
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def test_a_long_period_counts_spending_only_from_the_first_planned_month(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-03-31")
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"]
    for month in ("01", "02", "03"):
        c.transactions.record_outflow(f"2026-{month}-10", accounts["cib"].id, "1000", food.id)
    c.budgets.set_budget(food.id, "2026-03", "1200")      # the plan starts in March
    page = TestClient(create_app(c)).get("/budget?period=ytd&month=2026-03").text
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page.split('class="kpi-row', 1)[1]))
    assert "Planned and spent from 2026-03-01, the first month with a plan." in text
    spent = re.search(r"Spent YTD ([\d,]+) EGP", text).group(1)   # the Spent card (guideline 3.32 A08)
    assert Decimal(spent.replace(",", "")) == Decimal("1000")   # March only, not 3,000


def test_every_tab_says_why_a_backwards_custom_range_shows_this_month(c, monkeypatch):
    # Overview and Expense analysis said so; Budget and Investments fell back to the month silently.
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    c.account_flows.open_account("CIB", "BANK", "2026-09-01", "1000")
    c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "0")
    client = TestClient(create_app(c))
    for page in ("/", "/birdview/expenses", "/budget", "/investments"):
        html = client.get(f"{page}?period=custom&date_from=2026-08-01&date_to=2026-03-01").text
        assert "The end month must be the same as or after the start month." in html, page


def test_sample_period_plan_matches_its_saved_month_and_group_rows(c, monkeypatch):
    from lightning.samples import load_mohab_2026
    from lightning.ui.routes import budget

    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    load_mohab_2026(c)
    expected = c.budgets.plan_summary("2026-10")["planned"]
    assert expected > Decimal("30000")
    contexts = []
    original = budget.render

    def capture(request, template, **context):
        contexts.append(context)
        return original(request, template, **context)

    monkeypatch.setattr(budget, "render", capture)
    with TestClient(create_app(c)) as client:
        for period in ("month", "ytd", "all"):
            assert client.get(f"/budget?period={period}&month=2026-10").status_code == 200
            shown = contexts[-1]
            assert shown["period_budgeted"] == expected, period
            assert sum(row["budgeted"] for row in shown["group_totals"].values()) == expected, period
            assert shown["period_actual"] == Decimal("3410"), period
            assert shown["period_left"] == expected - Decimal("3410"), period
        assert client.get("/budget?period=custom&date_from=2026-10&date_to=2026-10").status_code == 200
        assert abs(contexts[-1]["period_budgeted"] - expected * Decimal(4) / Decimal(31)) < Decimal("0.01")
