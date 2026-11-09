"""The date picker's month opens the months, its year opens the years (feedback batch 004, T9)."""

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import require_chromium, chromium_executable

CHROMIUM = chromium_executable()


def _open_calendar(page, host):
    page.goto(host.launch_url)
    page.goto(host.origin + '/accounts/new')
    page.evaluate("document.getElementById('opening_balance_date').value = '2026-10-15'")
    page.locator('#opening_balance_date').click()
    page.locator('.date-popup').wait_for()


def test_the_title_opens_months_then_years_and_a_pick_comes_back_down(c):
    require_chromium()
    host = Host(lambda _: create_app(c)).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM))
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            _open_calendar(page, host)
            title = page.locator('.date-popup-title')
            assert title.inner_text() == 'October 2026'
            title.click()                                              # days -> months
            assert page.locator('.date-popup [data-month]').count() == 12
            page.locator('.date-popup-title').click()                  # the year -> years
            assert page.locator('.date-popup [data-year]').count() == 12
            page.locator('.date-popup [data-year="2025"]').click()     # a year -> months of 2025
            assert page.locator('.date-popup-title').inner_text() == '2025'
            page.locator('.date-popup [data-month="2"]').click()       # March -> its days
            assert page.locator('.date-popup-title').inner_text() == 'March 2025'
            page.locator('.date-popup [data-day="2025-03-14"]').click()
            assert page.locator('#opening_balance_date').input_value() == '2025-03-14'
            browser.close()
    finally:
        host.stop()


def test_escape_goes_up_one_level_before_closing(c):
    require_chromium()
    host = Host(lambda _: create_app(c)).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM))
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            _open_calendar(page, host)
            page.locator('.date-popup-title').click()
            page.locator('.date-popup-title').click()
            assert page.locator('.date-popup [data-year]').count() == 12
            page.keyboard.press('Escape')
            assert page.locator('.date-popup [data-day]').count() >= 28   # back to the days
            page.keyboard.press('Escape')
            assert page.locator('.date-popup').count() == 0
            browser.close()
    finally:
        host.stop()
