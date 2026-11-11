"""3AY9 (owner pick 2026-11-11): Budget shows a payday strip at the top from the salary's day until this month's plan is
saved. Saving the payday plan (or marking its review reviewed) ends it; a month whose salary has not come shows none."""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.planning.salary_day import payday_to_plan, review_identity, salary_review
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app


def _phone(c):
    app = create_app(c)
    mount_phone(app)

    async def as_phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return TestClient(as_phone)


@pytest.fixture
def mohab(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-05")   # October's salary arrived on the 1st
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    c = build(tmp_path / "t.db")
    load_mohab_2026(c)
    yield c
    c.db.close()


def test_the_strip_shows_after_the_salary_until_the_plan_is_saved(mohab):
    html = _phone(mohab).get("/budget").text
    strip = html[html.index('class="phone-row phone-payday-strip"'):]
    assert strip.startswith('class="phone-row phone-payday-strip" href="/payday"')
    assert "Plan this month" in strip[:300] and html.index("phone-payday-strip") < html.index('id="lead-heading"')
    salary = salary_review(mohab.db, date(2026, 10, 5))
    mohab.settings.set("review_item_" + review_identity(salary), json.dumps({"status": "reviewed"}, sort_keys=True))
    assert "phone-payday-strip" not in _phone(mohab).get("/budget").text   # the plan is saved: the strip is gone


def test_no_strip_before_this_month_s_salary(mohab, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-11")   # November's salary is not recorded yet
    from lightning.core.dates import today
    assert payday_to_plan(mohab.db, mohab.settings, today()) is None
    assert "phone-payday-strip" not in _phone(mohab).get("/budget").text
