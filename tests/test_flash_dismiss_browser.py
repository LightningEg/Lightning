"""Owner, 2026-11-14: a save message leaves by itself after 5 seconds, Undo or not, and its X closes it at once."""
from types import SimpleNamespace

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.fixture
def page_and_host(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-flash-session", csrf="test-flash-csrf")
    app = create_app(c)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}

    host = Host(lambda cfg: Guard(SessionGate(app, session), cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(host.launch_url)
                yield page, host
    finally:
        host.stop()


def test_a_save_message_with_undo_leaves_after_five_seconds_and_x_closes_it(page_and_host):
    from playwright.sync_api import expect
    page, host = page_and_host
    page.goto(host.origin + "/categories")
    button = page.locator("button[data-confirm-delete]").first
    button.click()
    page.locator('dialog.ask-dialog[open] [data-ask="yes"]').click()
    flash = page.locator("main > .flash:not(.error):not(.device-line)")
    expect(flash).to_have_count(1)
    expect(flash.locator(".flash-close")).to_be_visible()
    page.mouse.move(0, 799)  # not resting on the message
    expect(flash).to_have_count(0, timeout=8000)

    page.goto(host.origin + "/categories?msg=Saved.")
    flash = page.locator("main > .flash:not(.error):not(.device-line)")
    expect(flash).to_have_count(1)
    flash.locator(".flash-close").click()
    expect(flash).to_have_count(0, timeout=1000)


@pytest.fixture
def phone_page(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from lightning.ui.phone.router import mount_phone
    chromium = require_chromium()
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-flash-phone", csrf="test-flash-phone-csrf")
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
                page = browser.new_page(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True)
                page.goto(host.launch_url)
                yield page, host
    finally:
        host.stop()


def test_the_phone_message_leaves_too_and_its_x_is_a_full_size_target(phone_page):
    from playwright.sync_api import expect
    page, host = phone_page
    page.goto(host.origin + "/home?msg=Saved.")
    flash = page.locator(".phone-flash")
    expect(flash).to_be_visible()
    close = flash.locator(".flash-close")
    box = close.bounding_box()
    assert box["width"] >= 44 and box["height"] >= 44
    expect(flash).to_be_hidden(timeout=8000)

    page.goto(host.origin + "/home?msg=Saved.")
    expect(page.locator(".phone-flash")).to_be_visible()
    page.locator(".phone-flash .flash-close").tap()
    expect(page.locator(".phone-flash")).to_be_hidden(timeout=1000)
