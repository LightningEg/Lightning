"""BV-7AW (r37 W3, M2): Compare scenarios uses one measure, Cash planning's Lowest point ahead day by day, on the lead,
the headline and What changes, on the PC and the phone; a late salary shows on its lowest day."""
from __future__ import annotations

import html
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.planning.scenarios import compare_scenario, occurrence_key
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app

DAY, END = date(2026, 11, 14), date(2027, 2, 12)


@pytest.fixture
def mohab_now(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", DAY.isoformat())
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    load_mohab_2026(c)
    return c


def _text(app_html: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", app_html)))


def _page(c, phone: bool, **params) -> str:
    app = create_app(c)

    @app.middleware("http")
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)

    with TestClient(app) as client:
        response = client.get("/plan/scenarios", params=params)
    assert response.status_code == 200
    return _text(response.text)


@pytest.mark.parametrize("phone", [False, True])
def test_a_purchase_below_zero_says_how_short_and_never_no_shortfall(mohab_now, phone):
    c = mohab_now
    bank = next(a for a in c.accounts.list(active_only=True) if a.account_type.value == "BANK")
    base = compare_scenario(c.forecaster, DAY, END)
    amount = int(base.plan_low.closing) + 10_000
    result = compare_scenario(c.forecaster, DAY, END, purchase=str(amount), purchase_date="2026-11-20",
                              account_id=str(bank.id))
    month, low, on = result.scenario_plan_low
    assert low < 0 and on == "2026-11-20" and result.first_below_zero == ("2026-11-20", low)
    assert result.change == low - base.plan_low.closing

    page = _page(c, phone, purchase=str(amount), purchase_date="2026-11-20", account_id=str(bank.id))
    short = f"{-low:,.0f}"
    if not phone:
        assert f"You would be {short} short in November." in page
    assert "No shortfall" not in page and "Stays above zero" not in page
    assert "First day below zero" in page and "Lowest scheduled cash" not in page


@pytest.mark.parametrize("phone", [False, True])
def test_a_salary_late_inside_one_month_shows_its_lowest_day(mohab_now, phone):
    c = mohab_now
    payments, _ = c.forecaster.scheduled_inputs(DAY, END)
    salary = next(p for p in payments if p.item.is_income and p.due_date.startswith("2026-12"))
    result = compare_scenario(c.forecaster, DAY, END, income=occurrence_key(salary), delay="20")
    december = next(row for row in result.months if row[0] == "2026-12")
    # Month end is unchanged (the salary still lands in December); the lowest December day is lower by the salary.
    assert december[2] == december[1] - c.planning.amount_in_base(salary, salary.amount, DAY)
    page = _page(c, phone, what="income", income=occurrence_key(salary), delay="20")
    assert "Lowest scheduled cash" not in page and "No shortfall" not in page


def _get(c, path, phone=False, **params):
    app = create_app(c)

    @app.middleware("http")
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)

    with TestClient(app) as client:
        return client.get(path, params=params) if params else client.get(path)


@pytest.mark.parametrize("phone", [False, True])
def test_the_afford_date_counts_without_an_account_and_a_past_date_is_refused(mohab_now, phone):
    c = mohab_now
    payday = c.forecaster.forecast(DAY).next_income_date
    later = date.fromisoformat(payday).replace(day=10).isoformat()
    before = _text(_get(c, "/plan", phone, afford="30000").text)
    after = _text(_get(c, "/plan", phone, afford="30000", afford_date=later).text)
    assert "safe to spend until" in before and "safe to spend until" not in after
    assert "Your lowest point ahead would be" in after or "short in" in after
    past = _text(_get(c, "/plan", phone, afford="30000", afford_date="2025-01-01").text)
    assert "Pick today or a later date." in past and "Plan this purchase" not in past
    assert "Can I afford this?" in after and "Plan this purchase" in after


def test_plan_this_purchase_opens_the_one_off_form_and_lands_in_the_forecast(mohab_now):
    c = mohab_now
    page = _get(c, "/plan", afford="12345", afford_date="2027-01-10").text
    href = html.unescape(re.search(r'href="(/plan/items/new\?[^"]+)"', page).group(1))
    assert "frequency=ONCE" in href and "start_date=2027-01-10" in href and "amount=12345" in href
    form = _get(c, href).text
    assert 'value="12345"' in form and "2027-01-10" in form
    before = {m.month: m.commitments for m in c.forecaster.forecast(DAY).months}
    c.planning.create(kind="BILL", name="Purchase", amount="12345", frequency="ONCE", start_date="2027-01-10")
    after = {m.month: m.commitments for m in c.forecaster.forecast(DAY).months}
    assert after["2027-01"] - before["2027-01"] == 12345


def test_a_scenario_purchase_offers_plan_this_purchase(mohab_now):
    c = mohab_now
    bank = next(a for a in c.accounts.list(active_only=True) if a.account_type.value == "BANK")
    page = _get(c, "/plan/scenarios", purchase="5000", purchase_date="2026-12-05", account_id=str(bank.id)).text
    assert "Plan this purchase" in page and "start_date=2026-12-05" in html.unescape(page)
    assert "Plan this purchase" not in _get(c, "/plan/scenarios").text


def test_a_missing_rate_leaves_the_first_day_below_zero_unknown_not_an_error():
    from lightning.planning.scenarios import ScenarioResult
    result = ScenarioResult(None, None, None, None, ("x",), None, None, (),
                            (("2026-11", 100, None, (("2026-11-20", None), ("2026-11-30", -5))),))
    assert result.first_below_zero == ("2026-11-30", -5)
