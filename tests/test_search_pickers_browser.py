"""The actual PC/phone fields use the server matcher and keep their stored selections explicit."""
from pathlib import Path
import os
import shutil

import pytest

from lightning.runtime.http import Host
from lightning.ui.web import create_app


@pytest.mark.parametrize('phone', [False, True])
def test_scoped_account_category_owner_counterparty_and_instrument_fields(c, setup, phone):
    if os.environ.get('LIGHTNING_REQUIRE_BROWSER') == '1':
        from playwright.sync_api import sync_playwright
    else:
        sync_playwright = pytest.importorskip('playwright.sync_api').sync_playwright
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
            executable = shutil.which('chromium') or pw.chromium.executable_path
            if not Path(executable).is_file():
                if os.environ.get('LIGHTNING_REQUIRE_BROWSER') == '1':
                    pytest.fail('The required Chromium browser is missing')
                pytest.skip('Chromium is not installed')
            browser = pw.chromium.launch(executable_path=executable, args=['--no-sandbox'])
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


@pytest.mark.parametrize('phone',[False,True])
def test_import_picker_keeps_same_named_account_and_counterparty_choices_distinct(c,setup,phone):
    if os.environ.get('LIGHTNING_REQUIRE_BROWSER') == '1':
        from playwright.sync_api import sync_playwright
    else:
        sync_playwright=pytest.importorskip('playwright.sync_api').sync_playwright
    bank,wallet=setup[0]['cib'],setup[0]['wallet']
    party=c.counterparties.create(wallet.name)
    food=c.categories.get_by_code('EXP.PERSONAL.FOOD')
    batch,_=c.bank_imports.stage(bank.id,'identity.csv',f'Date,Counterparty,Amount\n2026-09-20,{wallet.name},-10\n'.encode())
    rid=c.bank_imports.preview(batch)[1][0]['_import_row_id']
    app=create_app(c)
    @app.middleware('http')
    async def frame(request,call_next):
        request.state.phone=phone
        return await call_next(request)
    host=Host(lambda _:app).start()
    try:
        with sync_playwright() as pw:
            executable=shutil.which('chromium') or pw.chromium.executable_path
            if not Path(executable).is_file():
                if os.environ.get('LIGHTNING_REQUIRE_BROWSER')=='1':
                    pytest.fail('The required Chromium browser is missing')
                pytest.skip('Chromium is not installed')
            browser=pw.chromium.launch(executable_path=executable,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':390 if phone else 1366,'height':900})
            page.goto(f'{host.origin}/accounts/{bank.id}/import/{batch}')
            input_=page.locator(f'#cp-{rid}')
            assert page.locator(f'#cp-pick-{rid}').input_value()==''
            input_.fill(wallet.name)
            menu=page.locator('#'+input_.get_attribute('aria-controls'))
            page.wait_for_function('(id)=>document.getElementById(id).querySelectorAll("[role=option]").length===2',arg=menu.get_attribute('id'))
            menu.get_by_role('option',name=wallet.name,exact=True).click()
            assert page.locator(f'#cp-pick-{rid}').input_value()==f'counterparty:{party}'
            category=page.locator(f'select[name="category_{rid}"]')
            category_input=category.locator('..').locator('input[role=combobox]')
            category_input.fill('Groceres')
            category_menu=page.locator('#'+category_input.get_attribute('aria-controls'))
            category_menu.locator(f'[data-value="{food.id}"]').click()
            before=c.reporting.account_balance(wallet.id)
            with page.expect_navigation(wait_until='domcontentloaded'):
                page.get_by_role('button',name='Post ready rows',exact=True).first.click()
            assert c.reporting.account_balance(wallet.id)==before
            txn_id=c.db.scalar('SELECT transaction_id FROM bank_import_rows WHERE id=?',(rid,))
            assert c.transactions.get(txn_id).type=='OUT'
            browser.close()
    finally:
        host.stop()
