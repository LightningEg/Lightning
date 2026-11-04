"""Phone Other preserves emergency liquidity sources and their access timing."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.core.dates import today
from lightning.runtime.http import Host
from lightning.ui.web import create_app


def test_phone_liquidity_other_opens_full_context(c, setup):
    chromium = Path('/opt/pw-browsers/chromium')
    executable = str(chromium) if chromium.exists() else shutil.which('chromium')
    if not executable:
        pytest.skip('Chromium is not installed')
    def holding(name, code, value, until=None):
        return SimpleNamespace(asset=name, class_code=code, value=value, locked_until=until)
    c.reserves.set_emergency_fund('5000')
    position = c.position.at(today())
    classes = (
        SimpleNamespace(name='Money Market Fund', items=[holding('Fund', 'FUND.MONEY_MARKET', Decimal('100'))]),
        SimpleNamespace(name='Certificates', items=[holding('Certificate A', 'DEPOSIT.CD', Decimal('200'), '2027-08-01'),
                                                    holding('Certificate B', 'DEPOSIT.CD', Decimal('300'), '2028-08-01')]),
        SimpleNamespace(name='Stocks', items=[holding('Stock', 'STOCK', Decimal('400'))]),
        SimpleNamespace(name='Gold', items=[holding('Unpriced gold', 'GOLD', None)]),
    )
    c.position.at = lambda as_of=None, *, match_payments=True: replace(position, classes=classes)
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
                    assert page.goto(host.origin + '/plan/reserves').status == 200
                    assert page.locator('html').get_attribute('lang') == ('ar-EG' if language == 'ar' else 'en')
                    disclosure = page.locator('#emergency-liquidity')
                    disclosure.locator('summary').click()
                    assert disclosure.locator('li').count() == 5  # four names and Other
                    other = disclosure.locator('li a')
                    assert other.is_visible() and other.bounding_box()['height'] >= 44
                    other.click()
                    page.wait_for_url('**/*liquidity_view=all*')
                    full = page.locator('#emergency-liquidity[open]')
                    assert full.count() == 1 and full.locator('li').count() == 7
                    assert full.get_by_text('Certificate A', exact=False).count() == 1
                    assert full.get_by_text('الأسهم' if language == 'ar' else 'Stocks', exact=False).count() == 1
                    assert full.locator('li').evaluate_all('es => es.every(e => e.scrollWidth <= e.clientWidth + 1)')
                    full.locator('li a').click()
                    page.wait_for_url('**/plan/reserves#emergency-liquidity')
                context.close()
            browser.close()
    finally:
        host.stop()
