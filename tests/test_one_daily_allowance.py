"""BV-12A: one "a day" allowance. Home's hero line gives Budget's own everyday per-day figure (owner, 2026-11-09,
IV-11E), never a second one; the phone's Budget shows the same everyday per-day figure as the PC's, from
EverydayBudget.per_day."""
from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.core.money import fmt
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.screens import said


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        patch.setenv("LIGHTNING_TODAY", "2026-10-04")
        c = build(tmp_path_factory.mktemp("daily") / "t.db")
        load_mohab_2026(c)
        yield c
        c.db.close()


def _phone(c):
    inner = create_app(c)
    mount_phone(inner)

    async def app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await inner(scope, receive, send)
    return TestClient(app)


def test_home_gives_budgets_own_per_day_figure(sample):
    everyday = sample.forecaster.everyday("2026-10", date(2026, 10, 4))
    html = _phone(sample).get("/home").text
    line = re.sub(r"<[^>]+>", "", re.search(r'<p class="phone-hero-line">(.*?)</p>', html, re.S).group(1))
    assert line.strip() == f"About {fmt(everyday.per_day, 0)} a day until payday on {said('2026-11-01')}.", line
    root = _phone(sample).get("/").text.split('class="phone-hero-line"', 1)[1][:200]  # the phone's / is Home: the same figure
    assert re.findall(r"About ([\d,]+) a day", root) == [fmt(everyday.per_day, 0)], root


def test_phone_and_pc_budget_show_the_same_per_day_figure(sample):
    everyday = sample.forecaster.everyday("2026-10", date(2026, 10, 4))
    figure = fmt(everyday.per_day, 0)
    pc = TestClient(create_app(sample)).get("/budget?period=month&month=2026-10").text
    phone = _phone(sample).get("/budget?period=month&month=2026-10").text
    assert re.search(rf"about {figure} a day", pc), figure
    assert re.search(rf"About {figure} a day for {everyday.days_left} days", phone), figure
