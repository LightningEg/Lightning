"""Live trade previews use the same number notation as server-rendered rows."""
import os
from pathlib import Path
import subprocess

from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


ROOT = Path(__file__).resolve().parents[1]


def test_number_runtime_under_a_german_locale():
    result = subprocess.run(["node", "tests/number-runtime.test.cjs"], cwd=ROOT,
                            env={**os.environ, "LANG": "de_DE.UTF-8"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    ui = ROOT / "lightning/ui"
    for path in [ui / "static/app.js", ui / "templates/budget.html"]:
        source = path.read_text()
        assert "NumberFormat(undefined" not in source
        assert "toLocaleString(undefined" not in source


def test_trade_preview_keeps_english_notation_in_a_german_browser(c, setup):
    chromium = require_chromium()
    from playwright.sync_api import sync_playwright, expect

    accounts, _ = setup
    asset = c.assets.create_investment("Example shares", "STOCK", "EXAMPLE")
    host = Host(lambda _: create_app(c)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(locale="de-DE", viewport={"width": 1366, "height": 768})
                page.goto(host.launch_url)
                page.goto(host.origin + f"/investments/new?kind=buy&account={accounts['thndr'].id}&asset={asset.id}")
                page.locator('[name="quantity"]').fill("10")
                page.locator('[name="total"]').fill("12345.67")
                expect(page.locator(".unit-price-preview")).to_have_value("1,234.567")
                assert page.evaluate("window.lightningNumber(-1234.5, {min: 2})") == "−1,234.50"
    finally:
        host.stop()
