"""3AY4: the phone is its own shell. Its base template never extends or includes the PC base; one cached stylesheet holds
its parts in cascade order; a PC-only page opens "This is on your PC" instead of PC markup; the status bar takes the
app bar's colour."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui import web
from lightning.ui.phone import router as phone_router
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app

TEMPLATES = Path(web.__file__).parent / "templates"


def test_the_phone_base_never_extends_or_includes_the_pc_base():
    text = (TEMPLATES / "phone" / "base.html").read_text()
    assert not re.search(r'\{%\s*(extends|include)\s+"(base|partials/layout)[^"]*"', text)
    assert 'extends "base.html"' not in text


def test_every_new_phone_screen_extends_a_base_that_hands_over_to_the_phone_frame():
    for name in ("home", "activity_home", "budget_flexible", "money", "money_accounts", "money_bills", "money_report",
                 "add_bills", "on_pc"):
        text = (TEMPLATES / "phone" / f"{name}.html").read_text()
        assert re.search(r'\{%\s*extends\s+"(phone/)?base\.html"', text), name


def test_the_phone_stylesheet_is_one_cached_bundle_in_cascade_order():
    parts = [p.replace("{rtl}", "") for p in web.PHONE_CSS]
    assert parts.index("style.css") < parts.index("phone.css") < parts.index("themes.generated.css")


def test_a_pc_only_page_opens_this_is_on_your_pc(c, monkeypatch):
    monkeypatch.setattr(phone_router, "BEST_ON_PC", ("/checks",))
    app = create_app(c)
    mount_phone(app)
    client = TestClient(app)
    page = client.get("/checks")
    assert page.status_code == 200 and "This is on your PC" in page.text and "Data checks works best on your PC" in page.text
    assert 'href="/money"' in page.text and "<table" not in page.text
    direct = client.get("/pc?return_to=/activity")
    assert 'class="phone-back" href="/activity"' in direct.text and "This works best on your PC" in direct.text
    assert 'class="phone-back" href="/money"' in client.get("/pc?return_to=//evil.example").text   # never an outside address


def test_no_page_is_pc_only_until_the_owner_says_so():
    assert phone_router.BEST_ON_PC == ()


@pytest.fixture
def phone_page(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = shutil.which("chromium") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    if not chromium:
        pytest.skip("Chromium is not installed")
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-own-base-session", csrf="test-own-base-csrf")
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
                page.goto(host.origin + "/money")
                yield page
    finally:
        host.stop()


def test_the_status_bar_takes_the_app_bars_colour_and_follows_a_theme_change(phone_page):
    page = phone_page
    first = page.evaluate("() => document.querySelector('meta[name=theme-color]')?.content")
    assert first and first.startswith("rgb(")
    page.evaluate("""() => { document.querySelector('.phone-appbar').style.background = 'rgb(10, 20, 30)';
        window.dispatchEvent(new CustomEvent('lightning:themechange', {detail: {id: 'x'}})); }""")
    page.wait_for_function("() => document.querySelector('meta[name=theme-color]').content === 'rgb(10, 20, 30)'")
