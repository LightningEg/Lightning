"""3AY6: Home. Always today; the Safe to spend hero, To do (three rows, one action each), Latest five, This month;
and the five states (first run, catch-up, payday, overspent, calm) each lead with what they should."""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
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
                                            safe_to_spend_parts=self.forecast.safe_to_spend_parts)
            return out
    monkeypatch.setattr(home, "ReviewInbox", Short)
    screen = home.build(c, day)
    assert screen.state == "overspent" and screen.safe < 0 and screen.per_day is None


def _page(sample, day="2026-10-04"):
    c, _ = _on(sample, day)
    app = create_app(c)
    mount_phone(app)
    return TestClient(app).get("/home")


def test_the_page_shows_the_hero_to_do_latest_and_this_month_in_that_order(sample):
    html = _page(sample).text
    assert html.index("Safe to spend") < html.index('id="todo-heading"') < html.index('id="latest-heading"') < html.index('id="month-heading"')
    assert html.count('class="phone-row') >= 4
    assert "Landlord" in html and "Pay ›" in html


def test_home_has_at_most_eight_figures(sample):
    html = _page(sample).text
    parts = [html.split('id="home-hero"', 1)[1].split("</section>", 1)[0].split(">", 1)[1],
             html.split('id="todo-heading"', 1)[1].split("</section>", 1)[0],
             html.split('id="month-heading"', 1)[1].split("</section>", 1)[0]]
    text = re.sub(r'<div class="phone-sheet-panel".*?</details>', " ", " ".join(parts), flags=re.S)  # the working is a sheet, not on the screen
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\d{4}-\d\d-\d\d|See all \d+", " ", text)  # dates and the count on "See all" are not figures
    figures = re.findall(r"\d[\d,]*(?:\.\d+)?(?!\d)(?!\s*(?:days?|bills?|more|items?))", text)  # amounts, not counts of days
    assert len(figures) <= 8 and not any("." in f for f in figures), figures  # whole EGP


def test_first_screen_holds_the_latest_row_in_one_and_a_fifth_screens(sample):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = shutil.which("chromium") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    if not chromium:
        pytest.skip("Chromium is not installed")
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
                "May be off: {n} days not recorded.", "Salary arrived", "Nothing recorded since {sa}. Two minutes to catch up.",
                "1 bill is long overdue. Two minutes to catch up.", "{n} bills are long overdue. Two minutes to catch up.",
                "Pay", "Catch up", "Sort", "To do", "Review"):
        assert translate(key, "ar") != key, key
