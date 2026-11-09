"""Five Planner recommendations stay readable and available in phone English and Arabic."""
from decimal import Decimal

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


def test_phone_planner_remainder_is_available_at_narrow_widths(c):
    executable = require_chromium()
    names = ('Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon')
    codes = ('STOCK', 'GOLD', 'FUND.GOLD', 'FUND.FIXED_INCOME', 'FUND.MONEY_MARKET')
    for name, code in zip(names, codes):
        c.investments.set_target_weight(name, Decimal('20'), c.assets.get_class_by_code(code).id)
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
                    assert rows.count() == 5
                    assert page.locator('.planner-popup-rows [data-planner-bucket]:visible').count() == 4
                    assert set(rows.evaluate_all('es => es.map(e => e.dataset.plannerBucket)')) == set(names)
                    summary = page.locator('details.planner-other > summary')
                    assert summary.evaluate('e => { const r=e.getBoundingClientRect(); return r.height >= 48 && r.left >= 0 && r.right <= innerWidth; }')
                    summary.click()
                    assert page.locator('.planner-popup-rows [data-planner-bucket]:visible').count() == 5
                    assert rows.evaluate_all('es => es.every(e => e.scrollWidth <= e.clientWidth + 1)')
                    assert page.locator('input[name=mode]').count() == 2
                context.close()
            browser.close()
    finally:
        host.stop()
