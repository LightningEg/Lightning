"""A person sees the correct native currency when choosing a bill's account."""

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.mark.parametrize('phone', [False, True], ids=['pc','phone'])
def test_bill_currency_label_tracks_the_account_picker(c, setup, phone):
    chromium = require_chromium()
    c.currencies.register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    c.fx.save('USD', '2026-12-31', '50')
    dollars = c.account_flows.open_account('Dollar cash', 'BANK', '2026-09-01', '100', currency='USD')
    app = create_app(c)
    @app.middleware('http')
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)
    host = Host(lambda _: app).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium)
            page = browser.new_page(viewport={'width': 390 if phone else 1366, 'height': 850})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(host.launch_url)
            page.goto(host.origin + '/plan/items/new?kind=BILL')
            assert page.locator('[data-plan-currency]').inner_text() == 'EGP'
            # Exercise the real user-record picker generated from the select.
            picker = page.locator('#account_id').locator('..').locator('input[role=combobox]')
            picker.fill('Dollar')
            page.get_by_role('option', name='Dollar cash', exact=True).click()
            assert page.locator('[data-plan-currency]').inner_text() == 'USD'
            picker.fill('')
            assert page.locator('[data-plan-currency]').inner_text() == 'EGP'
            picker.fill('Dollar')
            page.get_by_role('option', name='Dollar cash', exact=True).click()
            assert page.locator('[data-plan-currency]').inner_text() == 'USD'
            category = setup[1]['EXP.WORK.SOFTWARE']
            category_picker = page.locator('#category_id').locator('..').locator('input[role=combobox]')
            category_picker.fill(category.name)
            page.get_by_role('option', name=category.name, exact=True).click()
            page.locator('input[name=name]').fill('Foreign bill')
            page.locator('input[name=amount]').fill('10')
            page.locator('input[name=start_date]').fill('2027-01-05')
            page.locator('button.btn.primary').click()
            page.wait_for_url('**/plan/recurring*')
            assert 'Foreign bill' in page.locator('body').inner_text()
            assert c.planning.items()[0].account_id == dollars.id
            assert c.planning.items()[0].amount == 10
            assert not errors
            browser.close()
    finally:
        host.stop()
