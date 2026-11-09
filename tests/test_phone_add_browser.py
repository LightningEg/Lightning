"""J1 on the phone (IV-3AY7): from Home, a payment is saved in three taps (Add, a category chip, Save) with the amount
typed, and the person is back on Home. A real browser, the real sheet and script."""
from types import SimpleNamespace

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.fixture
def phone(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-add-session", csrf="test-add-csrf")
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
                page = browser.new_page(viewport={"width": 320, "height": 640}, is_mobile=True, has_touch=True)
                page.goto(host.launch_url)
                yield page, host
    finally:
        host.stop()


def test_a_payment_takes_three_taps_from_home(phone, c):
    page, host = phone
    before = c.db.scalar("SELECT COUNT(*) FROM transactions")
    page.goto(host.origin + "/home")
    taps = 0
    page.locator("a.phone-add").tap(); taps += 1
    page.wait_for_selector("#popup-amount")
    page.fill("#popup-amount", "42")
    page.locator("[data-category-chips] .phone-chip[data-category]:visible").first.tap(); taps += 1
    page.locator(".phone-save-bar .phone-save").tap(); taps += 1
    page.wait_for_url("**/home*")
    page.wait_for_selector(".phone-flash")
    assert taps == 3 and c.db.scalar("SELECT COUNT(*) FROM transactions") == before + 1
