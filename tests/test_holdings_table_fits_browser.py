"""The holdings table fits a 1366 px window without a sideways scroll."""

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import require_chromium, chromium_executable

CHROMIUM = chromium_executable()


def test_holdings_table_has_no_sideways_scroll_at_1366(c, setup):
    require_chromium()
    accounts, _ = setup
    for name, code in (("Commercial International Bank", "COMI"), ("Talaat Moustafa Group", "TMGH"),
                       ("Fawry for Banking Technology", "FWRY")):
        asset = c.assets.create_investment(name, "STOCK", code)
        c.investments.add_holding(accounts["thndr"].id, asset.id, "180", "950", "2025-09-10")
        c.assets.set_price(asset.id, "2026-09-30", "100")
    host = Host(lambda _: create_app(c)).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM))
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            page.goto(host.launch_url)
            page.goto(host.origin + '/investments?period=month&month=2026-09')
            wrap = page.locator('#holdings-table').locator('xpath=ancestor::div[contains(@class,"table-wrap")]')
            scroll, client = wrap.evaluate('e => [e.scrollWidth, e.clientWidth]')
            assert scroll <= client
            browser.close()
    finally:
        host.stop()
