"""The date picker's month opens the months, its year opens the years (feedback batch 004, T9)."""

import pytest
from datetime import date, timedelta

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import require_chromium, chromium_executable

CHROMIUM = chromium_executable()


@pytest.mark.parametrize('phone', [False, True])
@pytest.mark.parametrize('locale', ['en', 'ar'])
def test_transaction_calendar_starts_on_saturday(c, setup, phone, locale):
    executable = require_chromium()
    accounts, _ = setup
    c.settings.set('locale', locale)
    app = create_app(c)

    @app.middleware('http')
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)

    host = Host(lambda _: app).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=executable) as browser:
                page = browser.new_page(viewport={'width': 390 if phone else 1366, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(host.launch_url)
                page.goto(f'{host.origin}/accounts/{accounts["cib"].id}/transaction/new')
                assert page.locator('html').get_attribute('data-week-start') == '6'
                field = page.locator('input[name=date][data-date-ready]')
                field.focus()  # The phone makes date fields read-only when focused.
                # Saturday/Sunday starts, a six-row month, and leap day.
                for picked in ('2026-08-01', '2026-11-01', '2026-05-31', '2024-02-29'):
                    field.evaluate('(field, value) => { field.value = value; }', picked)
                    field.click()
                    panel = page.locator('.date-popup')
                    assert panel.locator('.date-popup-dow').first.inner_text() == ('السبت' if locale == 'ar' else 'Sat')
                    cells = panel.locator('[data-day]')
                    first = date.fromisoformat(picked).replace(day=1)
                    start = first - timedelta(days=(first.weekday() - 5) % 7)
                    shown = cells.evaluate_all('(cells) => cells.map(cell => cell.dataset.day)')
                    assert shown == [(start + timedelta(days=i)).isoformat() for i in range(len(shown))]
                    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                    assert last <= date.fromisoformat(shown[-1])
                    panel.locator(f'[data-day="{picked}"]').click()
                    assert field.input_value() == picked
                    assert panel.count() == 0
                assert not errors
    finally:
        host.stop()


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
