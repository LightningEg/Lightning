"""The phone's Budget (phone overhaul 2026-10-22): "Tell me if I am on pace, and where I am over".

A ring of how much of the plan is spent, the month stepper, one row for what is over plan, then a row per category,
over plan first. The percentages, the order and the sentences are worked out in routes/budget.py, not the template."""
import re
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials
from lightning.ui.routes import budget

from test_profile_app import create, token


@pytest.fixture(scope="module")
def phone(tmp_path_factory):
    folder = tmp_path_factory.mktemp("phone-budget")
    cfg = Credentials("http://127.0.0.1:9862")
    app = profile_app(cfg, folder / "docs", devices=Devices(folder / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        page = browser.get("/")
        browser.post("/demo", data={"__session": token(page.text, "__session")})
        yield browser


def test_the_ring_is_whole_percent_and_turns_rose_over_plan():
    within = budget._plan_ring(Decimal(1000), Decimal(850), Decimal(150))
    assert within["pct"] == 85 and not within["over"] and not within["wide"] and within["amount"] == Decimal(150)
    assert within["arc"] == pytest.approx(within["circumference"] * 0.85, abs=0.01)
    over = budget._plan_ring(Decimal(1000), Decimal(1120), Decimal(-120))
    assert over["pct"] == 112 and over["over"] and over["wide"] and over["amount"] == Decimal(120)
    assert over["arc"] == over["circumference"]  # a full turn, however far over
    assert budget._plan_ring(Decimal(1000), Decimal(-50), Decimal(1050))["pct"] == 0  # refunds never draw backwards
    assert budget._plan_ring(Decimal(0), Decimal(300), Decimal(-300)) is None  # nothing planned: no share to draw


def _lines():
    names = {1: "Eating out", 2: "Transport", 3: "Health", 4: "Fees", 5: "Untracked", 6: "Group"}
    depth = {6: 1}
    return SimpleNamespace(sections=[SimpleNamespace(lines=[
        SimpleNamespace(category_id=i, name=n, depth=depth.get(i, 2)) for i, n in names.items()])])


def test_categories_list_over_plan_first_then_the_closest_to_their_limit():
    figures = {  # spent, limit, left
        1: (2840, 2000, -840), 2: (90, 68, -22), 3: (900, 1000, 100), 4: (0, 15, 15), 5: (50, 0, -50), 6: (1, 1, 0)}
    periods = {i: {"spent": Decimal(s), "current_budget": Decimal(b), "left": Decimal(left)} for i, (s, b, left) in figures.items()}
    rows = budget._phone_categories(_lines(), {1, 2, 3, 4, 6}, periods, {6: [1, 2, 3, 4, 5]},
                                    SimpleNamespace(start_text="2026-10-01", end_text="2026-10-22"))
    assert [r["name"] for r in rows] == ["Eating out", "Transport", "Health", "Fees"]  # untracked and the group stay out
    assert [r["over"] for r in rows] == [True, True, False, False]
    assert rows[0]["amount"] == Decimal(840) and rows[0]["width"] == 100 and rows[2]["width"] == 90.0 and rows[3]["width"] == 0
    assert rows[0]["group_id"] == 6 and "category_id=1&date_from=2026-10-01&date_to=2026-10-22" in rows[0]["href"]


def test_the_over_plan_row_names_it_counts_it_and_offers_the_fix():
    rows = [{"over": True, "amount": Decimal(840), "name": "Dining out", "category_id": 1, "group_id": 6},
            {"over": True, "amount": Decimal(22), "name": "Transport", "category_id": 2, "group_id": 6},
            {"over": False, "amount": Decimal(5), "name": "Health", "category_id": 3, "group_id": 6}]
    both = budget._phone_over(rows, "2026-10", 22, None, None)
    assert both["title"] == {"text": "{n} categories are over plan", "values": {"n": 2}} and both["count"] == 2
    assert both["line"]["text"] == "{amt} over · {n} days left" and both["line"]["values"] == {"amt": "862", "n": 22}
    assert both["href"] == "/budget?month=2026-10&open_group=6#limit-1" and not both["popup"]  # type its limit
    one = budget._phone_over(rows[:1], "2026-10", 1, None, None)
    assert one["title"]["text"] == "{name} is over plan" and one["title"]["values"] == {"name": "Dining out"}
    assert one["line"]["text"] == "{amt} over · 1 day left"
    assert budget._phone_over(rows[:1], "2026-10", 0, None, None)["line"]["text"] == "{amt} over"  # a finished month
    assert budget._phone_over(rows[2:], "2026-10", 5, None, None) is None  # nothing over: no row at all


def test_adjust_opens_move_room_when_another_category_has_room():
    c = SimpleNamespace(budgets=SimpleNamespace(amounts_for=lambda month, loans=False: {1: (Decimal(2000),), 3: (Decimal(900),)}),
                        categories=SimpleNamespace(get=lambda category_id: SimpleNamespace(name="Health")))
    rows = [{"over": True, "amount": Decimal(840), "name": "Dining out", "category_id": 1, "group_id": 6}]
    over = budget._phone_over(rows, "2026-10", 9, c, SimpleNamespace(room={3: Decimal(900)}))
    assert over["popup"] and over["href"] == "/budget/move?month=2026-10&to=1&from=3&amount=840"
    short = budget._phone_over(rows, "2026-10", 9, c, SimpleNamespace(room={3: Decimal(100)}))  # not enough room anywhere
    assert not short["popup"] and short["href"].startswith("/budget?month=2026-10&open_group=6#limit-1")


def test_the_budget_page_leads_with_the_ring_then_the_stepper_then_the_categories(phone):
    html = phone.get("/budget").text
    assert "<table" not in html
    ring = re.search(r'class="phone-budget-ring[^"]*" role="img" aria-label="(\d+)% of the plan spent"', html)
    assert ring and f"<b>{ring.group(1)}%</b>" in html
    order = [html.index(marker) for marker in ('class="phone-budget-hero"', 'class="phone-period"', 'id="cats-heading"',
                                              'id="plan-heading"', 'id="groups-heading"')]
    assert order == sorted(order)
    assert 'class="phone-plan-bar' in html  # each category's meter (tests/test_phone_frame.py)
    assert 'href="/budget/fill?month=' in html and "Edit plan" in html
    assert re.search(r'<form method="post" action="/budget/rule/\d+" data-budget-rule>', html)  # a limit is typed beside its category
    if "phone-budget-over" in html:  # over plan: the first category row is an over-plan one, the other rows follow
        assert re.search(r'class="phone-row phone-cat is-over"', html)
        assert html.index("phone-budget-over") < html.index('id="cats-heading"')
        assert re.search(r'class="phone-needs-open" href="[^"]+"[^>]*>Adjust<', html)


def test_edit_plan_opens_every_group_where_its_limits_are_typed(phone):
    html = phone.get("/budget?open_group=all").text
    assert html.count('<details class="phone-group" open>') >= 1
    assert html.count('<details class="phone-group">') == 0
