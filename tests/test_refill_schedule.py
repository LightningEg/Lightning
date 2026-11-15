"""NF-3AZ7: the emergency refill as instalments after the upcoming needs, each with its forecast after-state, and a
manual alternative previewed with the same forecast. Nothing moves until Refill is pressed."""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.core.dates import today
from lightning.demo import build_demo
from lightning.ui.web import create_app

D = Decimal


def _demo(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-05")
    c = build(tmp_path / "schedule.db")
    build_demo(c)
    return c


def test_the_schedule_covers_the_gap_and_each_step_shows_its_after_state(tmp_path, monkeypatch):
    c = _demo(tmp_path, monkeypatch)
    free = c.position.at(today()).free_cash
    options = c.forecaster.refill_options(today(), free)
    gap = D(120000)
    rows = c.forecaster.refill_schedule(today(), gap, options)
    assert sum((r["amount"] for r in rows), D(0)) == gap and len(rows) >= 2
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)
    funds = [r["fund_after"] for r in rows]
    assert funds == sorted(funds)
    # The first instalment's after-state is Safe to spend with it moved today.
    assert rows[0]["safe_after"] == c.forecaster.forecast(today(), refill=rows[0]["amount"]).safe_to_spend
    # BT-7AV3: each later one counts the income expected by its date, so no row goes below zero.
    assert all(r["safe_after"] >= 0 and r["keeps_plan"] for r in rows)
    assert not rows[0]["lowest"] and all(r["lowest"] for r in rows[1:])
    assert c.forecaster.refill_schedule(today(), D(0), options) == []


def test_the_page_shows_instalments_and_a_manual_preview_and_moves_nothing(tmp_path, monkeypatch):
    c = _demo(tmp_path, monkeypatch)
    before = c.db.scalar("SELECT count(*) FROM transactions"), [dict(r) for r in c.db.all("SELECT * FROM cash_reserves")]
    client = TestClient(create_app(c))
    page = client.get("/plan/reserves").text
    assert "Refill in instalments" in page and "Emergency fund after" in page and "Safe to spend after" in page
    manual = client.get("/plan/reserves?refill_amount=1000").text
    assert "Moving 1,000" in manual and "Safe to spend becomes" in manual
    assert (c.db.scalar("SELECT count(*) FROM transactions"), [dict(r) for r in c.db.all("SELECT * FROM cash_reserves")]) == before
