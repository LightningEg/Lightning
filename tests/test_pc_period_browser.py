"""The PC period control keeps month navigation inside one track and submits the chosen period."""
from pathlib import Path
from types import SimpleNamespace
import shutil

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def test_pc_period_track_submits_months_and_custom_ranges(c, monkeypatch):
    pytest.importorskip('playwright')
    from playwright.sync_api import sync_playwright
    chromium = shutil.which('chromium') or ('/opt/pw-browsers/chromium' if Path('/opt/pw-browsers/chromium').exists() else None)
    if not chromium:
        pytest.skip('Chromium is not installed')
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-15')
    monkeypatch.setenv('LIGHTNING_PRICES_OFFLINE', '1')
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token='test-pc-period-session', csrf='test-pc-period-csrf')
    app = create_app(c)

    @app.get('/profiles/health')
    async def health():
        return {'locked': False, 'session': session.token}

    host = Host(lambda cfg: Guard(SessionGate(app, session), cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=['--no-sandbox']) as browser:
                page = browser.new_page(viewport={'width': 1366, 'height': 768})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(host.launch_url)
                page.goto(host.origin + '/?period=month&month=2026-10')
                control = page.locator('.site-period-control')
                assert control.locator('.period-buttons .month-stepper').count() == 1
                assert control.locator(':scope > .month-stepper').count() == 0
                control.locator('[data-month-shift="-1"]').click()
                assert 'month=2026-09' in page.url and 'period=month' in page.url
                control.locator('[data-month-select]').press('Enter')
                assert page.locator('.month-popup').is_visible()
                page.locator('.month-popup [data-value="2026-08"]').click()
                assert 'month=2026-08' in page.url and 'period=month' in page.url
                control.locator('[name=period][value=custom]').click()
                control.locator('[name=date_from]').click()
                page.locator('.month-popup [data-value="2026-07"]').click()
                control.locator('[name=date_to]').click()
                page.locator('.month-popup [data-value="2026-09"]').click()
                control.locator('button.btn[value=custom]').click()
                assert 'period=custom' in page.url and 'date_from=2026-07' in page.url and 'date_to=2026-09' in page.url
                control.locator('button[name=period][value=month]').click()
                assert 'period=month' in page.url and 'month=2026-10' in page.url
                assert control.locator('[data-month-shift="1"]').is_disabled()
                c.settings.set('locale', 'ar')
                page.set_viewport_size({'width': 1440, 'height': 900})
                page.goto(host.origin + '/?period=month&month=2026-10')
                assert page.locator('html').get_attribute('dir') == 'rtl'
                assert page.locator('.period-buttons .month-stepper').count() == 1
                control.locator('[data-month-shift="-1"]').click()
                assert 'period=month' in page.url and 'month=2026-09' in page.url
                c.settings.set('locale', 'en')
                page.goto(host.origin + '/settings?period=custom&date_from=2026-07&date_to=2026-09')
                ai = page.locator('#export-for-ai .site-period-control')
                assert ai.get_attribute('data-period-auto-apply') is not None
                ai.locator('[name=date_from]').click()
                page.locator('.month-popup [data-value="2026-08"]').click()
                assert 'period=custom' in page.url and 'date_from=2026-08' in page.url and 'date_to=2026-09' in page.url
                assert not errors
    finally:
        host.stop()
