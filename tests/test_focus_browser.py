"""One focus ring on the PC (IV-3BF1): Tab through the first stops of Overview and Transactions in a real browser
and find a visible ring (box-shadow or outline) on each; in forced-colors mode the outline is real."""
from __future__ import annotations

import re

import pytest
from tests.browser_support import require_chromium, chromium_executable

pytest.importorskip("playwright.sync_api")
CHROMIUM = chromium_executable()

RING = """() => { const el = document.activeElement; const s = getComputedStyle(el);
  return {tag: el.tagName, shadow: s.boxShadow, outline: s.outlineStyle, width: s.outlineWidth}; }"""


@pytest.fixture(scope="module")
def pc_page(tmp_path_factory):
    """A 1366 px browser on a dummy profile holding the sample household."""
    require_chromium()
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    root = tmp_path_factory.mktemp("pc-focus")
    host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0))).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM), args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.goto(host.launch_url)
            page.goto(host.origin + "/profiles/new")
            page.fill("input[name=name]", "Focus")
            page.fill("input[name=password]", "a dummy pc password")
            page.fill("input[name=confirm]", "a dummy pc password")
            page.fill("input[name=answer]", "Dummy")
            if page.locator("select[name=question]").count():
                page.select_option("select[name=question]", index=1)
            elif page.locator("input[name=question]").count():
                page.fill("input[name=question]", "Dummy question?")
            page.click("button[type=submit]")
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


def _stops(page, origin, path, forced):
    page.emulate_media(forced_colors="active" if forced else "none")
    page.goto(origin + path)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    found = []
    for _ in range(8):
        page.keyboard.press("Tab")
        found.append(page.evaluate(RING))
    return found


@pytest.mark.parametrize("path", ["/", "/transactions"])
def test_every_tab_stop_shows_a_ring(pc_page, path):
    page, origin = pc_page
    for stop in _stops(page, origin, path, forced=False):
        assert stop["shadow"] != "none" or stop["outline"] != "none", stop


@pytest.mark.parametrize("path", ["/", "/transactions"])
def test_high_contrast_ring_is_a_real_outline(pc_page, path):
    page, origin = pc_page
    for stop in _stops(page, origin, path, forced=True):
        assert stop["outline"] != "none" and stop["width"] != "0px", stop
