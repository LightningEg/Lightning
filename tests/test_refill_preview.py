"""BT-2AH: the emergency refill suggests only what keeps Safe to spend at or above zero, shows the consequence, and
keeps moving everything as a separate, explicit choice."""
import re
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.core.dates import today
from lightning.demo import build_demo
from lightning.ui.web import create_app

D = Decimal


def _demo(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-05")
    c = build(tmp_path / "refill.db")
    build_demo(c)
    return c


def test_the_forecast_what_if_matches_really_moving_the_money(tmp_path, monkeypatch):
    c = _demo(tmp_path, monkeypatch)
    emergency = next((r for r in c.reserves.list_active() if r["kind"] == "EMERGENCY"), None)
    set_aside = emergency["effective_allocated"] if emergency else D(0)
    predicted = c.forecaster.forecast(today(), refill=D("10000")).safe_to_spend
    assert predicted < c.forecaster.forecast(today()).safe_to_spend
    salary_target = c.budgets.emergency_fund("2026-11", None, schedule=c.schedules.view()).target
    c.reserves.set_emergency_fund(str(set_aside + 10000), salary_target)
    assert c.forecaster.forecast(today()).safe_to_spend == predicted  # the what-if is the forecast after the move


def test_the_suggested_refill_keeps_safe_to_spend_and_all_of_it_is_a_choice(tmp_path, monkeypatch):
    c = _demo(tmp_path, monkeypatch)
    free = c.position.at(today()).free_cash
    options = c.forecaster.refill_options(today(), free)
    assert options["all_after"] < 0 < options["before"]          # the audit's case: all free cash overdraws the plan
    assert 0 < options["safe"] < free and options["safe_after"] >= 0
    assert c.forecaster.forecast(today(), refill=options["safe"] + 1000).safe_to_spend < options["safe_after"]
    page = TestClient(create_app(c)).get("/plan/reserves").text
    suggested = re.search(r'refill-prompt.*?name="allocated" value="([\d,.]+)"', page, re.S).group(1)
    emergency = next((r for r in c.reserves.list_active() if r["kind"] == "EMERGENCY"), None)
    base = emergency["effective_allocated"] if emergency else D(0)
    first = c.forecaster.refill_options(today(), free, top_up=c.budgets.emergency_fund(
        "2026-11", base, schedule=c.schedules.view()).top_up)["first"]
    assert D(suggested.replace(",", "")) == base + first                  # IV-12AA2: the modest amount is filled
    assert "Safe to spend after:" in page and "Move more" in page and "anyway</button>" in page
