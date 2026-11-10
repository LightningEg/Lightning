"""BV-11L3: the review count has space and Add only has phone navigation."""
import pytest

from lightning.runtime.http import Host
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_review_count_has_a_gap_and_add_has_no_pc_tabs(c, monkeypatch, locale):
    executable = require_chromium()
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    load_mohab_2026(c)
    c.settings.set("locale", locale)
    app = create_app(c)
    mount_phone(app)

    async def phone_app(scope, receive, send):
        scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)

    host = Host(lambda _: phone_app).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=executable) as browser:
                page = browser.new_page(viewport={"width": 320, "height": 800})
                for width in (320, 360):
                    page.set_viewport_size({"width": width, "height": 800})
                    page.goto(host.origin + "/activity")
                    chip = page.locator('.phone-chip[href="/activity?tab=review"]')
                    assert chip.locator("span").inner_text()
                    if locale == "en":
                        assert chip.locator("span").inner_text() == "To review"
                    count_text = chip.locator("b").inner_text()
                    assert int("".join(ch for ch in count_text if ch.isdecimal())) > 0
                    page.wait_for_function("document.fonts.status === 'loaded'")
                    label = chip.locator("span").bounding_box()
                    count = chip.locator("b").bounding_box()
                    gap = max(count["x"] - label["x"] - label["width"], label["x"] - count["x"] - count["width"])
                    assert gap >= 4
                    for path in ("/accounts/add-transaction", "/accounts/add-transaction?pick=1"):
                        page.goto(host.origin + path)
                        assert page.locator("[role=tablist]").count() == 0
                        assert page.locator(".phone-tabbar .phone-tab").count() == 5
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        host.stop()
