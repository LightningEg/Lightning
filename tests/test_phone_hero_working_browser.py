"""NF-12AB4 (C06.1): on the phone, Home's Safe to spend, Money's Net worth and Budget's hero open their working as a
sheet: the rows the owning service returns (lightning/core/working.py) and one link to the figure's home."""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

from lightning.runtime.http import Host
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


def test_each_hero_opens_its_working(c, monkeypatch):
    executable = require_chromium()
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    from lightning.samples import load_mohab_2026
    load_mohab_2026(c)
    app = create_app(c)
    mount_phone(app)

    async def phone_app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    host = Host(lambda _: phone_app).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=executable)
            page = browser.new_context(viewport={"width": 360, "height": 800}, is_mobile=True, has_touch=True).new_page()
            for path, rows, home in (("/home", "Free cash", "/plan"), ("/money", "Cash you own", "/"),
                                     ("/budget", "Bills to pay", "/budget")):
                page.goto(host.origin + path)
                hero = page.locator("details.phone-sheet-row:has(.phone-lead) > summary").first
                panel = page.locator("details.phone-sheet-row:has(.phone-lead) .phone-sheet-panel").first
                assert not panel.is_visible(), path
                hero.click()
                assert panel.is_visible(), path
                assert rows in panel.inner_text() and "How it adds up" in panel.inner_text(), path
                assert panel.locator(f'a[href="{home}"]').count() == 1, path
            browser.close()
    finally:
        host.stop()
