"""BT-7AV (r37 W1, W2): saving done this month is counted once.

Owner, 2026-11-14: this month's Emergency fund top-up and Saving for goals are what the month asked on the 1st, less
what was moved in since, never below zero. So doing what the plan reserved leaves Safe to spend where it was, the
payday page's "Safe to spend stays at ..." is true after Confirm, and nothing is offered twice in a month. Money
taken out of a reserve does not raise this month's ask. The refill in instalments never goes below zero."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import ROUND_UP, Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning import reserves as reserves_module
from lightning.core.dates import now_iso, today
from lightning.demo import build_demo
from lightning.planning.forecast import emergency_fund
from lightning.ui.web import create_app

D = Decimal


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-14")
    c = build(tmp_path / "saving.db")
    build_demo(c)
    return c


def _safe(c):
    return c.forecaster.forecast(today()).safe_to_spend.quantize(D("1"))


def _fund(c):
    return emergency_fund(c.reserves, c.budgets, "2026-11", c.schedules.view())


def _emergency(c):
    return next(r for r in c.reserves.list_active() if r["kind"] == "EMERGENCY")


def _confirm(c):
    plan = c.funding.preview()
    c.funding.apply(plan["token"], {str(r["id"]): str(r["suggested"]) for r in plan["rows"]},
                    {str(r["id"]): str(r["suggested"]) for r in plan["reserves"]})


def test_refilling_by_the_top_up_leaves_safe_to_spend_and_asks_nothing_more(demo):
    c = demo
    before, top_up = _safe(c), _fund(c).top_up
    assert top_up > 0 and "Emergency fund top-up" in dict(c.forecaster.forecast(today()).safe_to_spend_parts)
    target = c.budgets.emergency_fund("2026-11", None, schedule=c.schedules.view()).target
    c.reserves.set_emergency_fund(str(_emergency(c)["allocated"] + top_up.quantize(D("1"), ROUND_UP)), target)
    assert _safe(c) == before                                  # was 51,420 -> 46,016 in r37
    assert _fund(c).top_up == 0
    assert "Emergency fund top-up" not in dict(c.forecaster.forecast(today()).safe_to_spend_parts)
    assert all(r["suggested"] == 0 for r in c.funding.preview()["reserves"])


def test_confirm_on_payday_leaves_safe_to_spend_and_is_not_offered_again(demo):
    c = demo
    c.settings.set("cash_funding_enabled", "1")
    before = _safe(c)
    with TestClient(create_app(c)) as client:
        page = client.get("/payday").text
    said = re.search(r"Safe to spend stays at ([\d,]+)", page).group(1)
    assert D(said.replace(",", "")) == before
    _confirm(c)
    assert _safe(c) == before                                  # was 38,172 in r37
    again = c.funding.preview()["proposal"]
    assert again["reserves"] == 0 and again["to_plan"] == 0    # r37: "Confirm to give 7,332 a job", again and again


def test_a_goal_filled_this_month_asks_only_the_rest(demo, monkeypatch):
    c = demo
    goal = c.reserves.create("New laptop", "24,000", due_date="2027-10-31")
    c.reserves.allocate(goal["id"], "6,000")                   # its set-up amount: not a move
    # Later moves, minutes after it was set up, count against this month's ask.
    later = (datetime.fromisoformat(now_iso()) + timedelta(minutes=5)).isoformat(timespec="seconds")
    monkeypatch.setattr(reserves_module, "now_iso", lambda: later)
    need = next(r["amount"] for r in c.forecaster.goal_needs("2026-11", today()) if r["id"] == goal["id"])
    assert need == D("1500.00")                                # 18,000 over 12 months
    before = _safe(c)
    c.reserves.allocate(goal["id"], "7,000")                   # 1,000 of the 1,500
    assert _safe(c) == before
    assert next(r["amount"] for r in c.forecaster.goal_needs("2026-11", today()) if r["id"] == goal["id"]) == 500
    c.reserves.allocate(goal["id"], "7,500")
    assert _safe(c) == before
    assert goal["id"] not in {r["id"] for r in c.forecaster.goal_needs("2026-11", today())}
    # A later month asks from what the goal holds now, spread as before (16,500 over 12).
    assert next(r["amount"] for r in c.forecaster.goal_needs("2026-12", today()) if r["id"] == goal["id"]) == D("1375.00")


def test_a_goal_created_empty_and_filled_on_payday_is_not_offered_again(demo, monkeypatch):
    """r37: a goal's 2,667 a month became 2,370 more after Confirm."""
    c = demo
    c.settings.set("cash_funding_enabled", "1")
    goal = c.reserves.create("Wedding", "36,000", due_date="2027-10-31")
    later = (datetime.fromisoformat(now_iso()) + timedelta(minutes=5)).isoformat(timespec="seconds")
    monkeypatch.setattr(reserves_module, "now_iso", lambda: later)
    before = _safe(c)
    offered = next(r["suggested"] for r in c.funding.preview()["reserves"] if r["id"] == goal["id"])
    assert offered == 3000
    _confirm(c)
    assert _safe(c) == before
    assert next(r["suggested"] for r in c.funding.preview()["reserves"] if r["id"] == goal["id"]) == 0


def test_money_taken_out_does_not_raise_this_months_ask(demo):
    c = demo
    ask = _fund(c).top_up
    target = c.budgets.emergency_fund("2026-11", None, schedule=c.schedules.view()).target
    c.reserves.set_emergency_fund(str(_emergency(c)["allocated"] - 5000), target)
    assert _fund(c).top_up == ask
    assert _fund(c).ongoing_top_up > ask                       # it shows from next month


def test_the_instalment_refill_never_goes_below_zero(demo):
    c = demo
    fund = _emergency(c)
    gap = _fund(c).target - fund["effective_allocated"]
    options = c.forecaster.refill_options(today(), min(gap, c.position.at(today()).free_cash))
    rows = c.forecaster.refill_schedule(today(), gap, options)
    assert len(rows) >= 2 and sum((r["amount"] for r in rows), D(0)) == gap
    assert all(r["safe_after"] >= 0 and r["keeps_plan"] for r in rows)   # r37: -51,420 and -78,273
    with TestClient(create_app(c)) as client:
        page = client.get("/plan/reserves").text
    schedule = page.split('id="refill-schedule"', 1)[1].split("</details>", 1)[0]
    assert "Lowest point ahead" in schedule and "−" not in schedule
