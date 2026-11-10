"""BV-11L2: Arabic time labels follow the plotted months, as A06.2 requires."""
import pytest

from lightning.runtime.http import Host
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_the_latest_trend_point_sits_in_its_months_column(c, monkeypatch, locale):
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
                page = browser.new_page(viewport={"width": 360, "height": 800}, reduced_motion="reduce")
                for path, chart, dot, labels in (
                    ("/money", ".phone-chart-trend", ".phone-chart-trend-dot.is-last", ".phone-chart-trend-x > span"),
                    ("/investments", ".chart-trend", ".chart-dot", ".chart-x > span"),
                ):
                    page.goto(host.origin + path)
                    page.wait_for_function("document.fonts.status === 'loaded'")
                    figure = page.locator(chart).first
                    point = figure.locator(dot).last.bounding_box()
                    newest = figure.locator(labels).last.bounding_box()
                    oldest = figure.locator(labels).first.bounding_box()
                    assert point and newest and oldest
                    x = point["x"] + point["width"] / 2
                    assert newest["x"] - 1 <= x <= newest["x"] + newest["width"] + 1
                    assert newest["x"] > oldest["x"]
                    # The plotted line ends at the same position as the focusable dot.
                    endpoint = figure.locator("polyline").first.evaluate("""line => {
                        const p = line.points.getItem(line.points.numberOfItems - 1);
                        return new DOMPoint(p.x, p.y).matrixTransform(line.getScreenCTM()).x;
                    }""")
                    assert abs(endpoint - x) < 1
                # The phone Report currently uses rows, with no time axis to mirror.
                page.goto(host.origin + "/money/report")
                assert page.locator(".chart-trend, .phone-chart-trend").count() == 0
    finally:
        host.stop()
