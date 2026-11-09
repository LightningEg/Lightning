"""BV-3BA (audit r26 F6): in Arabic a page header's start date sits to the right of its end date, no figure carries a
Latin comma between Arabic digits, and a counted noun agrees with its count (1, 2, 3 to 10, 11 and more)."""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from lightning.bootstrap import build
from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.i18n import translate
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.mark.parametrize("count,phrase", [(1, "بعد يوم واحد"), (2, "بعد يومين"), (3, "بعد 3 أيام"), (10, "بعد 10 أيام"),
                                          (11, "بعد 11 يوم"), (0, "بعد 0 يوم")])
def test_days_agree_with_their_count(count, phrase):
    assert translate("in {n} days", "ar", n=count) == phrase


@pytest.mark.parametrize("count,phrase", [(1, "دفعة واحدة"), (2, "دفعتين"), (3, "3 دفعات"), (11, "11 دفعة")])
def test_payments_agree_with_their_count(count, phrase):
    assert translate("{n} payments until {date}.", "ar", n=count, date="x").startswith(phrase)


def test_a_fraction_of_months_takes_the_singular():
    assert "0.8 شهر." in translate("{months} months of cover. Review your emergency reserve.", "ar", months="0.8")


def test_a_count_of_another_thing_is_left_alone():
    assert translate("by day {n}", "ar", n=3) == "لحد يوم 3"


def test_the_revaluation_label_is_arabic():
    assert not re.search(r"[A-Za-z]{3}", translate("Investment revaluation · month_end", "ar"))


@pytest.fixture
def arabic(tmp_path):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        patch.setenv("LIGHTNING_TODAY", "2026-10-04")
        c = build(tmp_path / "t.db")
        load_mohab_2026(c)
        c.settings.set("locale", "ar")
        session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                                  token="test-ar-session", csrf="test-ar-csrf")
        app = create_app(c)

        @app.get("/profiles/health")
        async def health():
            return {"locked": False, "session": session.token}
        gate = SessionGate(app, session)
        host = Host(lambda cfg: Guard(gate, cfg)).start()
        try:
            with sync_playwright() as p:
                with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                    page = browser.new_page(viewport={"width": 1366, "height": 900})
                    page.goto(host.launch_url)
                    yield SimpleNamespace(page=page, origin=host.origin)
        finally:
            host.stop()
            c.db.close()


@pytest.mark.parametrize("path", ["/", "/budget", "/birdview/expenses"])
def test_the_header_reads_start_date_first_from_the_right(arabic, path):
    page = arabic.page
    page.goto(arabic.origin + path)
    page.wait_for_selector(".page-dates bdi")
    boxes = page.evaluate("[...document.querySelectorAll('.page-dates bdi')].map(e => e.getBoundingClientRect().left)")
    assert len(boxes) == 2 and boxes[0] > boxes[1], boxes  # the first (start) date is the right-hand one


@pytest.mark.parametrize("path", ["/", "/budget", "/accounts", "/investments", "/plan"])
def test_no_figure_has_a_latin_comma_between_arabic_digits(arabic, path):
    page = arabic.page
    page.goto(arabic.origin + path)
    page.wait_for_timeout(300)
    assert not re.search(r"[٠-٩],[٠-٩]", page.evaluate("document.body.innerText"))
