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
    assert s.state == "current" and s.left == e.everyday_left
    assert s.pace_gap == e.everyday_spent - e.pace            # the PC's Everyday card says the same


def test_everyday_allowance_has_its_own_name_while_home_keeps_the_whole_plan(mohab):
    """BV-11L1: unpaid bills leave two valid figures, each under its own registry name."""
    from lightning.core.figures import FIGURES
    from lightning.ui.phone.screens import home
    from lightning.ui.web import _money

    day = date(2026, 10, 12)
    e = mohab.forecaster.everyday("2026-10", day)
    assert e.bills_to_pay > 0 and e.left != e.everyday_left
    assert home.build(mohab, day).left_in_plan == e.left
    assert screen.build(mohab, day).left == e.everyday_left
    app = create_app(mohab)
    mount_phone(app)
    client = TestClient(app)
    home_page = client.get("/home")
    budget_page = client.get("/budget/flexible")
    assert home_page.status_code == budget_page.status_code == 200
    assert 'Left in plan' not in home_page.text   # IV-11M3 (mockup v2.0): Home shows the everyday figure in a well, under its own name
    assert f'>{FIGURES["everyday_left"].label} <span aria-hidden="true">' in budget_page.text  # NF-12AB4: the hero opens its working
    assert f'>{_money(e.everyday_left, places=0)} <small>' in budget_page.text
    assert 'Left in plan' not in budget_page.text
    assert client.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False).status_code == 303
    assert 'المتبقي للصرف اليومي' in client.get("/budget/flexible").text
    assert 'المتبقي للصرف اليومي' in client.get("/home").text


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
    assert "Personal" in page and "Fixed bills and savings" in page and "<input"   # IV-11M5 (mockup v2.0) names not in page.split('id="cats-heading"')[1].split("</section>")[0]
    assert TestClient(app).get("/budget/flexible?month=garbage").status_code == 200


def test_needs_attention_holds_no_finished_category_and_no_category_twice(mohab):
    """BV-11F: a category spent exactly to its plan is done, not a need; one in Needs attention is not listed again;
    and no row's figure is a lone zero."""
    for day in (date(2026, 10, 12), date(2026, 10, 28)):
        s = screen.build(mohab, day, "2026-10")
        assert all(r.left != 0 and r.state in ("over", "ahead") for r in s.attention)
        assert not {r.category_id for r in s.attention} & {r.category_id for r in s.categories}
        assert all(r.state == "done" for r in s.categories if r.left == 0 and r.limit > 0)


def test_a_category_spent_to_its_plan_reads_as_done_never_a_lone_zero(mohab, monkeypatch):
    app = create_app(mohab)
    mount_phone(app)
    s = screen.build(mohab, date(2026, 10, 12), "2026-10")
    page = TestClient(app).get("/budget/flexible").text
    for r in s.categories:
        if r.state == "done":
            assert f'is-done' in page
    assert '<bdi class="fig">0</bdi>' not in page and '<bdi class="fig">٠</bdi>' not in page


def test_the_month_bar_parts_add_to_the_plan_and_the_donut_to_its_total(mohab):
    s = screen.build(mohab, date(2026, 10, 12), "2026-10")
    e = mohab.forecaster.everyday("2026-10", date(2026, 10, 12))
    b = s.month_bar
    assert b["spent"] + b["left"] == e.everyday_plan and b["over"] == max(e.everyday_spent - e.everyday_plan, 0)
    assert abs(b["w_spent"] + b["w_left"] + b["w_over"] - 100) < 1e-6
    d = s.spend
    assert len(d["segments"]) <= 5 and d["total"] == sum(g["value"] for g in d["segments"])
    assert abs(sum(g["share"] for g in d["segments"]) - 100) < 1e-6
    assert d["total"] == e.everyday_spent        # BV-12O: fixed costs paid sit inside their categories, never added again
    assert not any(g.get("fixed") for g in d["segments"])


def test_the_month_bar_shows_over_plan_in_its_own_part():
    from decimal import Decimal
    b = screen.month_bar(Decimal(1000), Decimal(1300))
    assert (b["spent"], b["left"], b["over"]) == (1000, 0, 300)
    assert screen.month_bar(Decimal(0), Decimal(0)) is None


def test_the_plan_list_types_a_limit_beside_each_everyday_category_and_saves_it(mohab):
    """3AY9: Make or Edit plan opens /budget/plan, one field per everyday category under its group; a field posts to
    /budget/rule/{id}, and the older page's addresses (open_group, make) land on this list."""
    import re
    app = create_app(mohab)
    mount_phone(app)
    client = TestClient(app)
    flexible = client.get("/budget?month=2026-10").text
    assert 'href="/budget/plan?month=2026-10"' in flexible and 'phone-budget-ring' not in flexible
    page = client.get("/budget/plan?month=2026-10").text
    forms = re.findall(r'<form class="phone-row phone-limit" method="post" action="/budget/rule/(\d+)" data-budget-rule id="limit-\1">', page)
    assert forms and page.count("<script") >= 1 and page.count("data-budget-rule]") == 1
    assert 'href="/budget/fill?month=2026-10"' in page and 'href="/budget?month=2026-10"' in page  # fill, and back
    for old in ("/budget?open_group=all&month=2026-10", "/budget?make=1&month=2026-10"):
        moved = client.get(old, follow_redirects=False)
        assert moved.status_code == 303 and moved.headers["location"] == "/budget/plan?month=2026-10"
    saved = client.post(f"/budget/rule/{forms[0]}", data={"month": "2026-10", "rule": "1234"}, headers={"X-Requested-With": "fetch"})
    assert saved.status_code == 204 and 'value="1234"' in client.get("/budget/plan?month=2026-10").text
