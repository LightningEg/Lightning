"""3AY6: Home. Always today; the Safe to spend hero, To do (three rows, one action each), Latest five, This month;
and the five states (first run, catch-up, payday, overspent, calm) each lead with what they should."""
from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.phone.screens import home
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        patch.setenv("LIGHTNING_TODAY", "2026-10-04")
        c = build(tmp_path_factory.mktemp("home") / "t.db")
        load_mohab_2026(c)
        yield c, patch
        c.db.close()


def _on(sample, day):
    c, patch = sample
    patch.setenv("LIGHTNING_TODAY", day)
    return c, date.fromisoformat(day)


def test_an_empty_profile_is_the_first_run_with_no_hero(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    c = build(tmp_path / "empty.db")
    screen = home.build(c, date(2026, 10, 4))
    assert screen.state == "first_run" and screen.safe is None
    c.db.close()


@pytest.mark.parametrize("day,state,first", [("2026-10-02", "payday", "bill"), ("2026-10-04", "calm", "bill"),
                                              ("2026-10-11", "catch_up", "bill")])
def test_the_state_follows_the_day_and_to_do_leads_with_bills(sample, day, state, first):
    screen = home.build(*_on(sample, day))
    assert screen.state == state
    assert len(screen.todo) <= home.TODO_SHOWN and screen.todo[0].kind == first
    assert all(row.action for row in screen.todo)  # one action each
    if state == "payday":
        assert any(row.kind == "payday" for row in screen.todo)


def test_catch_up_names_the_stale_bills_and_calm_does_not(sample):
    assert home.build(*_on(sample, "2026-10-11")).catch_up.stale_bills >= 1
    assert home.build(*_on(sample, "2026-10-04")).catch_up.stale_bills == 0


def test_an_overspent_day_has_a_negative_hero_and_says_so(sample, monkeypatch):
    c, day = _on(sample, "2026-10-04")
    real = home.ReviewInbox

    class Short(real):
        def items(self, on, **kw):
            out = super().items(on, **kw)
            self.forecast = SimpleNamespace(safe_to_spend=-1200, next_income_date=self.forecast.next_income_date,
                                            safe_to_spend_parts=self.forecast.safe_to_spend_parts,
                                            safe_to_spend_working=self.forecast.safe_to_spend_working)
            return out
    monkeypatch.setattr(home, "ReviewInbox", Short)
    screen = home.build(c, day)
    assert screen.state == "overspent" and screen.safe < 0


def _page(sample, day="2026-10-04"):
    c, _ = _on(sample, day)
    app = create_app(c)
    mount_phone(app)
    return TestClient(app).get("/home")


def test_the_page_shows_the_hero_to_do_latest_and_this_month_in_that_order(sample):
    html = _page(sample).text
    assert html.index("Safe to spend") < html.index('id="todo-heading"') < html.index('id="latest-heading"') < html.index('id="month-heading"')
    assert html.count('class="phone-row') >= 4
    assert "Landlord" in html and re.search(r"Pay <svg class=\"chevron\"", html)


def test_home_has_at_most_eight_figures(sample):
    html = _page(sample).text
    parts = [html.split('id="home-hero"', 1)[1].split('id="todo-heading"', 1)[0].split(">", 1)[1],  # the hero, not To do twice
             html.split('id="todo-heading"', 1)[1].split("</section>", 1)[0],
             html.split('id="month-heading"', 1)[1].split("</section>", 1)[0]]
    text = re.sub(r'<div class="phone-sheet-panel".*?</details>', " ", " ".join(parts), flags=re.S)  # the working is a sheet, not on the screen
    text = re.sub(r"<[^>]+>", " ", text)
    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    text = re.sub(rf"\d{{4}}-\d\d-\d\d|\b\d{{1,2}} (?:{months})\b(?: \d{{4}})?|See all \d+", " ", text)  # dates (1 Nov) and "See all" are not figures
    figures = re.findall(r"\d[\d,]*(?:\.\d+)?(?!\d)(?!\s*(?:days?|bills?|more|items?))", text)  # amounts, not counts of days
    assert len(figures) <= 8 and not any("." in f for f in figures), (figures, text)  # whole EGP


def test_first_screen_holds_the_latest_row_in_one_and_a_fifth_screens(sample):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    c, _ = _on(sample, "2026-10-04")
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-home-session", csrf="test-home-csrf")
    app = create_app(c)
    mount_phone(app)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}
    gate = SessionGate(app, session)
    gate.phone = True
    host = Host(lambda cfg: Guard(gate, cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
                page.goto(host.launch_url)
                page.goto(host.origin + "/home")
                page.wait_for_selector(".phone-latest .phone-txn")
                # 1.2 screens of content: the tab bar always covers the foot of the screen, so a screen is the window
                # above it, and the last section must end within 1.2 of those.
                above_tabs = page.evaluate("document.querySelector('.phone-tabbar').getBoundingClientRect().top")
                end = page.evaluate("document.querySelector('#month-heading').getBoundingClientRect().bottom + scrollY")
                assert end <= 1.2 * above_tabs, (end, above_tabs)
                top = page.evaluate("document.querySelector('.phone-latest .phone-txn').getBoundingClientRect().top")
                assert top < 600, top
    finally:
        host.stop()


def test_every_home_sentence_has_an_arabic_form():
    from lightning.ui.i18n import translate
    for key in ("Home", "Three steps to your first answer", "Your salary account", "Your payday", "Your first payment",
                "Salary arrived", "{n} days not recorded", "1 bill long overdue", "{n} bills long overdue",
                "About {amt} a day until payday on {sa}.", "About {amt} a day for {n} days.",
                "Pay", "Catch up", "Sort", "To do", "Open"):
        assert translate(key, "ar") != key, key


def test_add_sheet_returns_to_its_slot_and_offers_bills(sample):
    """3AY7: the Add slot carries the page it was opened from; the sheet says Move, and Pay a bill lists what is due."""
    c, _ = _on(sample, "2026-10-04")
    app = create_app(c)
    mount_phone(app)
    client = TestClient(app)
    home = client.get("/home").text
    assert "/accounts/add-transaction?return_to=/home" in home
    from test_phone_capture import _phone
    sheet = _phone(c).get("/accounts/add-transaction?return_to=/home").text
    assert "phone-pay-bill" in sheet and ">Move<" in sheet and ">Transfer<" not in sheet
    bills = client.get("/add/bills?return_to=/home")
    assert bills.status_code == 200 and "/plan/items/" in bills.text


def test_home_month_bar_adds_to_the_plan_and_agrees_with_left_in_plan(c, monkeypatch):
    """IV-11D2: the bar under This month is the plan's spent and left; its parts add to the plan."""
    from datetime import date
    from lightning.samples import load_mohab_2026
    from lightning.ui.phone.screens import home as screen
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-12")
    load_mohab_2026(c)
    s = screen.build(c, date(2026, 10, 12))
    b = s.month_bar
    assert b and b["spent"] + b["left"] == b["plan"] and b["left"] == max(s.left_in_plan, 0)


def test_every_to_do_row_has_a_figure_and_a_verb_and_the_hero_says_a_day(sample):
    """IV-11E (guideline C11.1): a To do row is the thing's name, its figure (an amount or a count), when, and one verb
    that says what happens, never "Review"; the hero's line is about how much a day, Budget's own figure (BV-12A)."""
    from lightning.planning import bill_state
    from lightning.workflows.todo import todo_rows
    c, day = _on(sample, "2026-10-04")
    inbox = home.ReviewInbox(c)
    items = inbox.items(day)
    bills = bill_state.open_bills(c.planning, day, bill_state.SOON_DAYS)
    rows = todo_rows(c, day, bills, items, bill_state.catch_up(c, day, bills), paid_today=True)
    assert len(rows) >= 8
    for row in rows:
        assert row.action and row.action != "Review", row
        assert row.amount is not None or row.count is not None or row.days is not None, row
    screen = home.build(c, day)
    assert screen.todo and all(r.action != "Review" for r in screen.todo)
    html = _page(sample).text
    line = re.sub(r"<[^>]+>", "", re.search(r'<p class="phone-hero-line">(.*?)</p>', html, re.S).group(1))
    assert "a day" in line, line
    section = html.split('id="todo-heading"', 1)[1].split("</section>", 1)[0]
    for row in re.findall(r'<a class="phone-row.*?</a>', section, re.S):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row))
        assert re.search(r"\d", text) and "Review" not in text, text


def test_days_not_recorded_is_a_to_do_row_not_the_hero_line(sample):
    """IV-11E: catch-up says how many days in To do; the hero keeps its figure a day."""
    screen = home.build(*_on(sample, "2026-10-11"))
    assert screen.state == "catch_up" and screen.per_day is not None
    html = _page(sample, "2026-10-11").text
    line = re.search(r'<p class="phone-hero-line">(.*?)</p>', html, re.S).group(1)
    assert "not recorded" not in line and "a day" in line


def test_the_payday_meter_reads_budgets_own_everyday_figures(sample):
    """IV-11D1 (C06.1): under Safe to spend, everyday money gone (fill) against the pace by today (tick), from the same
    EverydayBudget the hero's line and Budget read; rose only when Budget says spending is ahead of its pace."""
    c, day = _on(sample, "2026-10-04")
    e = c.forecaster.everyday("2026-10", day)
    meter = home.build(c, day).meter
    assert meter is not None and e.everyday_plan > 0
    assert meter.spent == round(float(min(e.everyday_spent / e.everyday_plan, 1) * 100), 1)
    assert meter.pace == round(float(min(e.pace / e.everyday_plan, 1) * 100), 1)
    assert meter.ahead == (e.pace_gap > 0)
    html = _page(sample).text
    hero = html.split('id="home-hero"', 1)[1].split('id="todo-heading"', 1)[0]
    assert f'width:{meter.spent:.1f}%' in hero and f'inset-inline-start:{meter.pace:.1f}%' in hero
    assert ("phone-pay-meter is-ahead" in hero) == meter.ahead


def test_no_meter_without_a_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    c = build(tmp_path / "empty.db")
    assert home.build(c, date(2026, 10, 4)).meter is None
    c.db.close()


def test_see_all_lists_every_to_do_row_and_home_links_to_it(sample):
    """IV-3AY14: /todo lists every row todo_rows returns, in order; Home's See all opens it, not the PC's Needs you."""
    from lightning.ui.phone.screens import todo
    c, day = _on(sample, "2026-10-04")
    rows = todo.build(c, day).rows
    screen = home.build(c, day)
    assert len(rows) == screen.todo_total and rows[:2] == screen.todo[:2]
    app = create_app(c)
    mount_phone(app)
    client = TestClient(app)
    page = client.get("/todo")
    assert page.status_code == 200
    body = page.text[page.text.index('<h1>'):]
    assert len(re.findall(r'class="phone-row[ "]', body)) == len(rows)
    for r in rows:
        assert r.href.replace("&", "&amp;") in body
    if screen.todo_total > len(screen.todo):
        assert 'href="/todo"' in client.get("/home").text
    assert 'href="/needs-you"' not in client.get("/home").text
