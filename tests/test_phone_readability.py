"""Computed phone layout regressions from the sample profile, at the narrow supported widths."""
from __future__ import annotations

import re

import pytest
from tests.browser_support import require_chromium, chromium_executable

pytest.importorskip("playwright.sync_api")
CHROMIUM = chromium_executable()


@pytest.fixture(scope="module")
def phone_page(tmp_path_factory):
    require_chromium()
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    root = tmp_path_factory.mktemp("phone-readability")
    host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM))
            page = browser.new_page(viewport={"width": 360, "height": 800}, is_mobile=True, has_touch=True)
            page.goto(host.launch_url)
            page.goto(host.origin + "/profiles/new")
            page.fill("input[name=name]", "Phone audit")
            page.fill("input[name=password]", "a dummy phone password")
            page.fill("input[name=confirm]", "a dummy phone password")
            page.fill("input[name=answer]", "Dummy")
            if page.locator("select[name=question]").count():
                page.select_option("select[name=question]", index=1)
            elif page.locator("input[name=question]").count():
                page.fill("input[name=question]", "Dummy question?")
            page.click("form[action='/profiles/new'] button[type=submit]")
            recovery = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
            if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count():
                page.fill("input[name=recovery]", recovery)
            page.click("form[action='/profiles/confirm'] button[type=submit]")
            page.goto(host.origin + "/")
            page.evaluate("""async () => {
              const token = document.querySelector('meta[name=lightning-session]').content;
              await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: token})});
            }""")
            yield page, host.origin
            browser.close()
    finally:
        host.stop()


@pytest.mark.parametrize("width", [320, 360])
def test_phone_content_fits_and_controls_remain_readable(phone_page, width):
    page, origin = phone_page
    page.set_viewport_size({"width": width, "height": 800})

    page.goto(origin + "/counterparties")
    page.locator('section[aria-labelledby="cp-list"] .phone-sheet-row > summary').first.click()   # a name's sheet (3AY17)
    save = page.locator('.phone-sheet-row[open] form:has(input[name=alias]) button').first
    assert save.is_visible()
    assert save.bounding_box()["height"] >= 48
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    # Spending (3AN12): the first page is the lead and rows; the charts load when "More analysis" opens and must fit too
    page.goto(origin + "/birdview/expenses")
    assert page.locator(".cluster-bars, .treemap, .cal-months").count() == 0  # nothing heavy on the first page
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator(".phone-sheet-row > summary").first.click()
    page.wait_for_selector(".phone-sheet-more .multiple, .phone-sheet-more .cal-months")
    label = page.locator(".phone-sheet-more .multiple-head b, .phone-sheet-more .cal-day").first
    assert label.evaluate("el => parseFloat(getComputedStyle(el).fontSize)") >= 12
    panel = page.locator(".phone-sheet-panel")
    assert panel.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
