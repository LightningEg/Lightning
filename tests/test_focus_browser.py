"""IV-3BF1: keyboard focus is visible on PC pages and the profile gate, including High Contrast."""
import re

import pytest

from tests.browser_support import require_chromium


@pytest.fixture(scope="module")
def focus_page(tmp_path_factory):
    chromium = require_chromium()
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    root = tmp_path_factory.mktemp("keyboard-focus")
    host = Host(lambda cfg: profile_app(cfg, root / "docs", devices=Devices(root / "app", port=0))).start()
    try:
        with sync_playwright() as pw:
            with pw.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(viewport={"width": 1366, "height": 768})
                page.set_default_timeout(5000)
                page.goto(host.launch_url)
                page.goto(host.origin + "/profiles/new")
                for name, value in {"name": "Focus", "password": "dummy focus password", "confirm": "dummy focus password",
                                    "answer": "Dummy"}.items():
                    page.locator(f"input[name={name}]").fill(value)
                if page.locator("select[name=question]").count():
                    page.select_option("select[name=question]", index=1)
                else:
                    page.fill("input[name=question]", "Dummy question?")
                page.click("button[type=submit]")
                recovery = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
                if page.locator("input[name=recovery][type=text]").count():
                    page.fill("input[name=recovery]", recovery)
                page.click("form[action='/profiles/confirm'] button[type=submit]")
                page.goto(host.origin + "/")
                page.evaluate("""async () => {
                  const token = document.querySelector('meta[name=lightning-session]').content;
                  await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: token})});
                }""")
                yield page, host.origin
    finally:
        host.stop()


@pytest.mark.parametrize("path", ["/", "/transactions", "/profiles/new"])
@pytest.mark.parametrize("locale", ["en", "ar"])
@pytest.mark.parametrize("forced_colors", ["none", "active"])
def test_tab_stops_have_visible_focus(focus_page, path, forced_colors, locale, tmp_path):
    page, origin = focus_page
    page.goto(origin + "/")
    page.evaluate("""async locale => {
      const token = document.querySelector('meta[name=lightning-session]').content;
      await fetch('/settings/locale', {method: 'POST', body: new URLSearchParams({__session: token, locale})});
    }""", locale)
    page.emulate_media(forced_colors=forced_colors)
    page.goto(origin + path)
    assert page.locator("html").get_attribute("lang").split("-")[0] == locale
    # Start the sequence at the document rather than a field's autofocus.
    page.evaluate("document.activeElement.blur()")
    for stop in range(8):
        page.keyboard.press("Tab")
        focused = page.evaluate("""() => {
          const el = document.activeElement, s = getComputedStyle(el);
          return {tag: el.tagName, html: el.outerHTML.slice(0, 180), visible: el.checkVisibility(),
            keyboard: el.matches(':focus-visible'), shadow: s.boxShadow, outline: s.outlineStyle,
            width: parseFloat(s.outlineWidth), color: s.outlineColor};
        }""")
        assert focused["tag"] != "BODY", (path, stop, focused)
        assert focused["visible"] and focused["keyboard"], (path, stop, focused)
        if forced_colors == "active":
            assert focused["outline"] == "solid" and focused["width"] >= 2, (path, stop, focused)
            assert focused["color"] not in ("transparent", "rgba(0, 0, 0, 0)"), focused
        else:
            # A transparent outline or an unrelated component shadow is not a focus indicator.
            assert "rgba(11, 138, 95, 0.28)" in focused["shadow"], (path, stop, focused)
    page.screenshot(path=str(tmp_path / "focus.png"))
