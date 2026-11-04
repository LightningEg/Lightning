"""The actual PC/phone fields use the server matcher and keep their stored selections explicit."""
from pathlib import Path

import pytest

from lightning.runtime.http import Host
from lightning.ui.web import create_app


@pytest.mark.parametrize('phone', [False, True])
def test_scoped_account_category_owner_counterparty_and_instrument_fields(c, setup, phone):
    from playwright.sync_api import sync_playwright
    if not Path('/usr/bin/chromium').exists():
        pytest.skip('Chromium is not installed')
    accounts, _ = setup
    person = c.counterparties.create('أحمد', kind='PERSON')
    c.counterparties.create('Talabat')
    asset = c.assets.create_investment('Commercial International Bank', 'STOCK', 'COMI')
    app = create_app(c)

    @app.middleware('http')
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)

    host = Host(lambda _: app).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
            page = browser.new_page(viewport={'width':390 if phone else 1366,'height':900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            path = f'/accounts/{accounts["cib"].id}/transaction/new'
            for kind, selector, query, expected in [
                ('transfer', 'select[name=to_account_id]', 'Walet', str(accounts['wallet'].id)),
                ('out', 'select[name=category_id]', 'Groceres', str(c.categories.get_by_code('EXP.PERSONAL.FOOD').id)),
                ('out', 'select[name=owner_id]', 'احمد', str(person)),
            ]:
                page.goto(host.origin+path+'?kind='+kind)
                select = page.locator(selector)
                details = select.locator('xpath=ancestor::details[1]')
                if details.count() and not details.evaluate('(el)=>el.open'):
                    details.locator('summary').click()
                if phone and selector == 'select[name=category_id]':
                    page.locator('[data-chip-other]').click()
                input_ = select.locator('..').locator('input[role=combobox]')
                input_.fill(query)
                menu = page.locator('#'+input_.get_attribute('aria-controls'))
                page.wait_for_function('(id)=>!document.getElementById(id).hidden', arg=menu.get_attribute('id'))
                assert select.input_value() == ''
                choice = menu.locator(f'[data-value="{expected}"]')
                choice.click()
                assert select.input_value() == expected
            page.goto(host.origin+path+'?kind=out')
            input_ = page.locator('#popup-counterparty')
            input_.fill('Talbt')
            menu = page.locator('#'+input_.get_attribute('aria-controls'))
            menu.get_by_role('option', name='Talabat', exact=True).click()
            assert input_.input_value() == 'Talabat'
            page.goto(host.origin+'/investments/new?kind=buy')
            select = page.locator('select[name=asset_id]')
            input_ = select.locator('..').locator('input[role=combobox]')
            input_.fill('Commercial Internatinal Bank')
            menu = page.locator('#'+input_.get_attribute('aria-controls'))
            menu.locator(f'[data-value="{asset.id}"]').click()
            assert select.input_value() == str(asset.id)
            page.evaluate("""() => { const original = window.fetch; window.fetch = (url, options) => {
                if (url !== '/search/picker') return original(url, options);
                return new Promise(resolve => { window.releasePicker = () => original(url, options).then(resolve); });
            }; }""")
            input_.fill('Commercial Internatinal')
            page.wait_for_function('typeof window.releasePicker === "function"')
            input_.press('Escape')
            page.evaluate('window.releasePicker()')
            page.wait_for_function("() => document.querySelector('select[name=asset_id]').parentElement.querySelector('input').getAttribute('aria-expanded') === 'false'")
            assert menu.is_hidden()
            assert not errors
            browser.close()
    finally:
        host.stop()
