"""Health's existing alert bands reach the inbox without chart work or duplicate actions."""
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.memo import request_cache
from lightning.planning.health import LIMIT_LABELS
from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox

DAY = date(2026, 12, 27)


def _household(c, setup):
    accounts, cats = setup
    for month in ("09", "10", "11"):
        c.transactions.record_inflow(f"2026-{month}-01", accounts["cib"].id, "1000", cats["EXP.WORK.SALARY"].id)
    c.planning.create(kind="BILL", name="Rent", amount="800", frequency="MONTHLY", start_date="2027-01-01")
    c.planning.create(kind="LOAN", name="Car", amount="400", frequency="MONTHLY", start_date="2027-01-05",
                      payment_count="100")
    c.health.set_limit("debt_to_cash", "20", alert_raw="25")


def test_real_ratios_match_the_health_page_and_visibility_decisions_do_not_post(c, setup):
    _household(c, setup)
    before = c.db.conn.total_changes
    inbox = ReviewInbox(c)
    with request_cache(c.db):
        figures = c.health.figures(DAY)
        alerts = inbox.items(DAY)
    expected = {"debt_to_cash", "debt_to_net_worth", "fixed_costs_to_income", "loan_payments_to_income"}
    assert {f.key for f in figures if f.band == "alert"} >= expected
    selected = {key: next(i for i in alerts if i["label"] == f"{LIMIT_LABELS[key]} needs you") for key in expected}
    assert c.db.conn.total_changes == before
    for key, item in selected.items():
        assert item["href"] == f"/financial-health#health-{key}"
        assert "% · Needs you above " in item["detail"]
    reviewed = selected["debt_to_cash"]
    count = c.db.scalar("SELECT COUNT(*) FROM transactions")
    inbox.decide(reviewed["review_id"], "reviewed", DAY)
    assert reviewed["review_id"] not in {i["review_id"] for i in inbox.items(DAY)}
    assert reviewed["review_id"] not in {i["review_id"] for i in inbox.items(date(2026, 12, 28))}
    other = selected["fixed_costs_to_income"]
    inbox.decide(other["review_id"], "snoozed", DAY, "2026-12-30")
    assert other["review_id"] not in {i["review_id"] for i in inbox.items(date(2026, 12, 29))}
    assert other["review_id"] in {i["review_id"] for i in inbox.items(date(2026, 12, 30))}
    inbox.decide(reviewed["review_id"], "restore", DAY)
    assert reviewed["review_id"] in {i["review_id"] for i in inbox.items(DAY)}
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == count


@pytest.mark.parametrize("band,value", [("watch", Decimal("60")), ("good", Decimal("40")), (None, None)])
def test_watch_good_and_unknown_figures_stay_quiet(c, setup, monkeypatch, band, value):
    figure = next(f for f in c.health.figures(DAY) if f.key == "fixed_costs_to_income")
    monkeypatch.setattr(c.health, "figures", lambda day: (replace(figure, value=value, band=band),))
    assert ReviewInbox(c)._health_alerts(DAY, []) == []


def test_savings_alerts_reuse_existing_actions_and_explain_an_unusable_rate(c, setup, monkeypatch):
    figures = {f.key: f for f in c.health.figures(DAY)}
    savings = replace(figures["savings_rate"], band="alert", value=Decimal("5"))
    planned = replace(figures["planned_savings_rate"], band="alert", value=Decimal("4"))
    monkeypatch.setattr(c.health, "figures", lambda day: (savings, planned))
    existing = [{"label": "November 2026 saved less than your target"},
                {"label": "This month's plan is short for your goals"}]
    assert ReviewInbox(c)._health_alerts(DAY, existing) == []
    assert {i["label"] for i in ReviewInbox(c)._health_alerts(DAY, [])} == {
        "Savings rate needs you", "Planned savings rate needs you"}
    savings = replace(savings, value=None, gap="200 more went out than the 100 that came in")
    monkeypatch.setattr(c.health, "figures", lambda day: (savings,))
    item = ReviewInbox(c)._health_alerts(DAY, [])[0]
    assert item["detail"] == "200 more went out than the 100 that came in. 2026-11."
    assert "%" not in item["detail"]


def test_current_figures_avoid_historical_position_reads_and_cache_invalidates_after_settings(c, setup, monkeypatch):
    _household(c, setup)
    original = c.position.at
    calls = []
    def tracked(day, *, match_payments=True):
        calls.append((day, match_payments))
        return original(day, match_payments=match_payments)
    monkeypatch.setattr(c.position, "at", tracked)
    with request_cache(c.db):
        first = c.health.figures(DAY)
        assert calls and all(day == DAY and not match for day, match in calls)
        calls.clear()
        assert c.health.figures(DAY) == first and not calls
        c.health.set_limit("debt_to_cash", "", no_limit=True)
        assert next(f for f in c.health.figures(DAY) if f.key == "debt_to_cash").band is None
        assert calls
        assert c.health.overview(DAY)["figures"] == c.health.figures(DAY)


@pytest.mark.parametrize("phone,locale", [(False, "en"), (True, "en"), (False, "ar"), (True, "ar")])
def test_alert_pages_explain_the_band_and_link_to_the_matching_health_row(c, setup, phone, locale):
    _household(c, setup)
    c.settings.set("locale", locale)
    app = create_app(c)
    @app.middleware("http")
    async def surface(request, call_next):
        request.state.phone = phone
        return await call_next(request)
    client = TestClient(app)
    page = client.get("/needs-you")
    assert page.status_code == 200
    assert 'href="/financial-health#health-debt_to_cash"' in page.text
    assert "Debt to cash needs you" in page.text if locale == "en" else "محتاج انتباهك" in page.text
    assert "Needs you above" in page.text if locale == "en" else "محتاج انتباهك فوق" in page.text
    assert 'id="health-debt_to_cash"' in client.get("/financial-health").text
