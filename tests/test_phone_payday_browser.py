"""The phone payday review previews bills and funding without assigning cash."""
from pathlib import Path
import shutil

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.runtime.http import Host
from lightning.ui.web import create_app


def test_phone_payday_preview_and_enable(c, setup, monkeypatch):
    executable = shutil.which('chromium') or str(Path('/opt/pw-browsers/chromium'))
    if not Path(executable).exists():
        pytest.skip('Chromium is not installed')
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-01')
    accounts, cats = setup
    food = cats['EXP.PERSONAL.FOOD'].id
    c.budgets.set_budget(food, '2026-12', '500', schedule=c.schedules.view())
    c.planning.create(kind='BILL', name='Preview rent', amount='100', frequency='ONCE',
                      start_date='2026-12-05', account_id=accounts['cib'].id, category_id=food)
    c.planning.create(kind='INCOME', name='Next salary', amount='2000', frequency='ONCE',
                      start_date='2026-12-20', account_id=accounts['cib'].id,
                      category_id=cats['EXP.WORK.SALARY'].id)
    app = create_app(c)
    async def phone_app(scope, receive, send):
        scope.setdefault('state', {})['phone'] = True
        await app(scope, receive, send)
    host = Host(lambda _: phone_app).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=executable)
            for language in ('en', 'ar'):
                c.settings.set('locale', language)
                c.settings.set('cash_funding_enabled', '0')
                context = browser.new_context(viewport={'width': 320, 'height': 800}, is_mobile=True, has_touch=True)
                context.add_cookies([{'name': 'lightning_ui_locale', 'value': language, 'url': host.origin}])
                page = context.new_page()
                before = c.db.scalar('SELECT count(*) FROM cash_funding')
                for width in (320, 360):
                    page.set_viewport_size({'width': width, 'height': 800})
                    page.goto(host.origin + '/payday')
                    assert page.locator('html').get_attribute('lang') == ('ar-EG' if language == 'ar' else 'en')
                    assert page.get_by_text('Preview rent', exact=False).count() == 1
                    assert page.locator('form[action="/payday/apply"] input[name^="category_"]').first.is_disabled()
                    assert page.locator('form[action="/payday/apply"] button[type=submit]').count() == 0
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.locator('form[action="/payday/enable"] button').click()
                page.wait_for_load_state('networkidle')
                assert page.locator('form[action="/payday/apply"] input[name^="category_"]').first.is_enabled()
                assert page.locator('form[action="/payday/apply"] button[type=submit]').count() == 1
                assert c.db.scalar('SELECT count(*) FROM cash_funding') == before
                context.close()
            browser.close()
    finally:
        host.stop()
