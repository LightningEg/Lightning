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


def test_categories_are_in_order_of_need_over_plan_then_ahead_of_pace_then_by_usual_spending():
    """3AN7: over plan (largest overspend first), then ahead of the month's pace, then the rest by what each usually
    costs (its three-month average, else its limit); an untracked line and a group stay out."""
    figures = {  # spent, limit, left
        1: (2840, 2000, -840), 2: (90, 68, -22), 3: (900, 1000, 100), 4: (0, 15, 15), 5: (50, 0, -50), 6: (1, 1, 0)}
    periods = {i: {"spent": Decimal(s), "current_budget": Decimal(b), "left": Decimal(left)} for i, (s, b, left) in figures.items()}
    period = SimpleNamespace(start_text="2026-10-01", end_text="2026-10-22")
    rows = budget._phone_categories(_lines(), {1, 2, 3, 4, 6}, periods, {6: [1, 2, 3, 4, 5]}, period)
    assert [r["name"] for r in rows] == ["Eating out", "Transport", "Health", "Fees"]  # no pace, no averages: by limit
    assert [r["over"] for r in rows] == [True, True, False, False]
    assert rows[0]["amount"] == Decimal(840) and rows[0]["width"] == 100 and rows[2]["width"] == 90.0 and rows[3]["width"] == 0
    assert rows[0]["group_id"] == 6 and "category_id=1&date_from=2026-10-01&date_to=2026-10-22" in rows[0]["href"]
    # Ahead of pace (10 points or more, not over) comes before the rest; the rest follow their usual spending.
    usual = {3: Decimal(50), 4: Decimal(700)}
    ahead = budget._phone_categories(_lines(), {1, 2, 3, 4, 6}, periods, {6: [1, 2, 3, 4, 5]}, period, Decimal(40), usual, "2026-10")
    assert [r["name"] for r in ahead] == ["Eating out", "Transport", "Health", "Fees"]  # Health is 90% spent at 40% of the month
    assert [bool(r["risk"]) for r in ahead] == [False, False, True, False]
    calm = {i: {**p, "spent": Decimal(0), "left": p["current_budget"]} for i, p in periods.items()}
    by_use = budget._phone_categories(_lines(), {1, 2, 3, 4, 6}, calm, {}, period, Decimal(10), usual, "2026-10")
    assert [r["name"] for r in by_use] == ["Eating out", "Fees", "Transport", "Health"]  # usual: 2000 (its limit), 700, 68 (its limit), 50
    assert by_use[1]["payments"] == "/budget/category/4/payments?month=2026-10"
    assert "return_to=%2Fbudget%3Fmonth%3D2026-10" in by_use[1]["see_all"] and "month=2026-10&" in by_use[1]["see_all"]


def test_a_long_list_shows_what_needs_a_look_and_the_biggest_usual_rows_the_rest_say_how_many_are_on_track():
    row = lambda n, over=False, risk=False: {"name": n, "over": over, "risk": risk}
    short = [row(str(i)) for i in range(5)]
    assert budget._split_rows(short) == (short, [])  # five or fewer show whole
    long = [row("over", over=True), row("ahead", risk=True)] + [row(str(i)) for i in range(7)]
    shown, rest = budget._split_rows(long)
    assert [r["name"] for r in shown] == ["over", "ahead", "0", "1"] and len(rest) == 5
    needy = [row(f"o{i}", over=True) for i in range(6)] + [row("x"), row("y")]
    assert len(budget._split_rows(needy)[0]) == 6  # every needy row shows, however many


def test_one_strip_sits_under_the_stepper_at_a_time():
    assert budget._strip(True, {"x": 1}, True, False) == "undo"
    assert budget._strip(False, {"x": 1}, True, False) == "raise"  # a decision waits before what is over
    assert budget._strip(False, {"x": 1}, False, False) == "over"
    assert budget._strip(False, None, False, True) == "first"
    assert budget._strip(False, None, False, False) == ""


def test_day_one_reads_the_plan_over_the_month_not_a_wall_of_zeros(monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-01")
    month = SimpleNamespace(key="month")
    line = budget._day_one(True, month, "2026-11", Decimal(0), Decimal(25599), 30)
    assert line == {"text": "New month: {amt} over {n} days", "values": {"amt": "25,599", "n": 30}}
    assert budget._day_one(True, month, "2026-11", Decimal(40), Decimal(25599), 30) is None  # money has moved
    assert budget._day_one(True, month, "2026-10", Decimal(0), Decimal(25599), 31) is None   # another month
    assert budget._day_one(False, month, "2026-11", Decimal(0), Decimal(0), 30) is None      # no plan


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
    c = SimpleNamespace(budgets=SimpleNamespace(amounts_for=lambda month, loans=False, schedule=None: {1: (Decimal(2000),), 3: (Decimal(900),)}),
                        schedules=SimpleNamespace(view=lambda: None),
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
    order = [html.index(marker) for marker in ('class="phone-budget-hero"', 'class="phone-period"', 'class="phone-note phone-budget-line"',
                                              'id="cats-heading"')]
    assert order == sorted(order)
    assert 'class="phone-plan-bar' in html  # each category's meter (tests/test_phone_frame.py)
    assert "Edit plan" in html
    # View, then edit (IV-3AL2): the page lists each category once and has no field; Edit plan shows the plan's
    # figures and the groups, where a limit is typed beside its category.
    assert 'id="groups-heading"' not in html and 'id="plan-heading"' not in html and "data-budget-rule" not in html
    edit = phone.get("/budget?open_group=all").text
    assert 'id="cats-heading"' not in edit and edit.index('id="plan-heading"') < edit.index('id="groups-heading"')
    assert 'href="/budget/fill?month=' in edit
    assert re.search(r'<form method="post" action="/budget/rule/\d+" data-budget-rule>', edit)
    if "phone-budget-over" in html:  # over plan: the first category row is an over-plan one, the other rows follow
        assert re.search(r'class="phone-row phone-sheet-summary phone-cat is-over"', html)
        assert html.index("phone-budget-over") < html.index('id="cats-heading"')
        assert re.search(r'class="phone-needs-open" href="[^"]+"[^>]*>Adjust<', html)


def test_edit_plan_opens_every_group_where_its_limits_are_typed(phone):
    html = phone.get("/budget?open_group=all").text
    assert html.count('<details class="phone-group" open>') >= 1
    assert html.count('<details class="phone-group">') == 0


def test_a_category_row_opens_its_sheet_and_see_transactions_keeps_budget_and_the_month(phone):
    """3AN7: a row is a sheet (spent of limit, pace, last payments, its limit, See transactions); See transactions keeps
    Budget chosen and the month on the stepper, never "Custom range"."""
    html = phone.get("/budget").text
    assert 'class="phone-sheet-row"' in html and 'class="phone-row phone-sheet-summary phone-cat' in html
    assert 'data-fold-src="/budget/category/' in html  # the last three payments load when the sheet opens
    assert re.search(r'<form method="post" action="/budget/rule/\d+" class="phone-form">', html) and ">Save limit<" in html
    link = re.search(r'href="(/transactions\?category_id=\d+&amp;month=\d{4}-\d{2}&amp;return_to=[^"]+)"', html)
    assert link and ">See transactions<" in html
    page = phone.get(link.group(1).replace("&amp;", "&")).text
    assert re.search(r'class="phone-tab is-chosen" href="/budget" aria-current="page"', page)
    assert not re.search(r'class="phone-tab is-chosen" href="/transactions"', page)
    assert re.search(r'<summary class="phone-period-now"[^>]*>\d{4}-\d{2}</summary>', page)  # the month, not a range
    assert re.search(r'class="phone-back" href="/budget\?month=\d{4}-\d{2}"', page) and ">Budget<" in page


def test_a_sheets_last_payments_load_apart_and_an_empty_month_offers_last_month(phone):
    html = phone.get("/budget").text
    src = re.search(r'data-fold-src="(/budget/category/(\d+)/payments\?month=([\d-]+))"', html)
    fragment = phone.get(src.group(1)).text
    assert "<html" not in fragment  # a fragment for the sheet, no frame
    assert "Last payments" in fragment or "Last month" in fragment or "Nothing spent here yet" in fragment
    empty = phone.get(f"/budget/category/{src.group(2)}/payments?month=2020-01").text
    assert "Nothing spent here yet this month." in empty and "Last payments" not in empty
