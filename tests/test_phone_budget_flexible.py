"""3AY9: Budget, flexible first. The hero is everyday money, the list is flexible categories with left as the figure,
and bills and loans are one Fixed costs row that never moves the pace."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.phone.screens import budget as screen
from lightning.ui.web import create_app


@pytest.fixture
def mohab(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-12")
    load_mohab_2026(c)
    return c


def test_the_hero_is_everyday_money_and_agrees_with_the_pc(mohab):
    c = mohab
    s = screen.build(c, date(2026, 10, 12), "2026-10")
    e = c.forecaster.everyday("2026-10", date(2026, 10, 12))
    assert s.state == "current" and s.left == e.everyday_plan - e.everyday_spent
    assert s.pace_gap == e.everyday_spent - e.pace            # the PC's Everyday card says the same


def test_fixed_costs_are_one_row_and_no_category_row_is_a_bill_or_loan(mohab):
    c = mohab
    s = screen.build(c, date(2026, 10, 12), "2026-10")
    view = c.budgets.month_view("2026-10", schedule=c.schedules.view())
    fixed = {l.category_id for sec in view.sections for l in sec.lines if l.from_loans or l.from_bills}
    assert s.fixed_count > 0 and s.fixed_planned > 0
    assert not fixed & {r.category_id for r in s.categories}
    assert [r.left for r in s.categories] == sorted(r.left for r in s.categories)   # least left first
    assert len(s.attention) <= screen.ATTENTION


def test_a_past_month_has_no_needs_attention(mohab):
    past = screen.build(mohab, date(2026, 11, 12), "2026-10")
    assert past.state == "past" and not past.attention


def test_a_profile_without_a_plan_gets_the_plan_step_not_a_figure(c):
    empty = screen.build(c, date(2026, 10, 12), "2026-10")
    assert empty.state == "no_plan" and empty.left is None and not empty.categories


def test_the_page_renders_in_the_phone_and_never_a_pc_template(mohab):
    app = create_app(mohab)
    mount_phone(app)
    page = TestClient(app).get("/budget/flexible").text
    assert "Your categories" in page and "Fixed costs" in page and "<input" not in page.split('id="cats-heading"')[1].split("</section>")[0]
    assert TestClient(app).get("/budget/flexible?month=garbage").status_code == 200
