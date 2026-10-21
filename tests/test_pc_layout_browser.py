"""PC layout checks in a real browser, on the sample household at 1366 px (3S1, 3C, 3S2): Settings › Sale factors does
not scroll sideways, and no chart writes two end labels on top of each other."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
CHROMIUM = Path("/opt/pw-browsers/chromium")
if not CHROMIUM.exists():
    CHROMIUM = Path(shutil.which("chromium") or str(CHROMIUM))

# Text boxes of the labels at the right end of a chart; two that share area are drawn on each other.
OVERLAPS = """() => {
  const found = [];
  for (const plot of document.querySelectorAll('.chart-plot, .pace-plot')) {
    const text = (el) => el.querySelector('small, b') || el;
    const labels = [...plot.querySelectorAll('.chart-end, .pace-end')].map(text).filter((el) => el.getBoundingClientRect().width);
    for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
      const a = labels[i].getBoundingClientRect(), b = labels[j].getBoundingClientRect();
      const across = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const down = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (across > 1 && down > 1) found.push([labels[i].innerText.trim(), labels[j].innerText.trim()]);
    }
  }
  return found; }"""


@pytest.fixture(scope="module")
def pc_page(tmp_path_factory):
    """A 1366 px browser on a dummy profile holding the sample household."""
    if not CHROMIUM.exists():
        pytest.skip("Chromium is not installed")
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    root = tmp_path_factory.mktemp("pc-layout")
    host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0))).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM), args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.goto(host.launch_url)
            page.goto(host.origin + "/profiles/new")
            page.fill("input[name=name]", "Layout")
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


def test_sale_factors_do_not_scroll_sideways(pc_page):
    page, origin = pc_page
    for width in (1366, 1024):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(origin + "/settings?section=valuations")
        assert page.locator(".factor-table").count() == 1
        assert page.locator(".factor-table td.num > small").count()  # the sample holds a locked certificate
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width


def test_no_chart_draws_two_end_labels_on_each_other(pc_page):
    page, origin = pc_page
    page.set_viewport_size({"width": 1366, "height": 900})
    page.goto(origin + "/investments")
    holdings = sorted(set(page.evaluate("[...document.querySelectorAll('a[href^=\"/investments/holding/\"]')].map(a => a.getAttribute('href'))")))
    assert holdings
    checked = 0
    for href in [*holdings, "/accounts/currencies?currency=USD", "/budget"]:
        page.goto(origin + href)
        checked += page.locator(".chart-end, .pace-end").count()
        assert page.evaluate(OVERLAPS) == [], href
    assert checked  # there were labels to check
