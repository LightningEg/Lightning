"""Five Planner recommendations stay readable and available in phone English and Arabic."""
from decimal import Decimal

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


def test_phone_planner_risk_levels_fit_narrow_widths(c):
    executable = require_chromium()
    names = ('Low risk', 'Medium risk', 'High risk')
    for name in names:
        c.investments.set_target_weight(name, Decimal('20'))
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
                context = browser.new_context(viewport={'width': 320, 'height': 800}, is_mobile=True, has_touch=True)
                page = context.new_page()
                for width in (320, 360):
                    page.set_viewport_size({'width': width, 'height': 800})
                    assert page.goto(host.origin + '/investments/planner?amount=1000').status == 200
                    assert page.locator('html').get_attribute('lang') == ('ar-EG' if language == 'ar' else 'en')
                    rows = page.locator('.planner-popup-rows [data-planner-bucket]')
                    assert page.locator('.planner-popup-rows [data-planner-bucket]:visible').count() == 3
                    assert set(rows.evaluate_all('es => es.map(e => e.dataset.plannerBucket)')) == set(names)
                    assert rows.evaluate_all('es => es.every(e => e.scrollWidth <= e.clientWidth + 1)')
                    assert page.locator('input[name=mode]').count() == 2
                context.close()
            browser.close()
    finally:
        host.stop()
