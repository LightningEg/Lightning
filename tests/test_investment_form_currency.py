"""BT-12AM: the currency displayed on general trade forms agrees with posted cash."""
from decimal import Decimal
import json
import re

import pytest
from fastapi.testclient import TestClient
from lightning.database.currencies import CurrencyRegistry
from lightning.ui.web import create_app


@pytest.fixture
def book(c):
    CurrencyRegistry(c.db).register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    c.fx.save('USD', '2026-12-31', '50')
    broker = c.account_flows.open_account('Dollar broker', 'BROKERAGE', '2026-09-01', '1000', currency='USD')
    asset = c.assets.create_investment('Dollar fund', 'FUND.EQUITY', 'USDTEST', currency='USD')
    return broker, asset


@pytest.mark.parametrize('phone', [False, True])
@pytest.mark.parametrize('kind', ['buy', 'sell', 'dividend', 'return_of_capital', 'holding', 'bonus_or_split'])
def test_prefilled_form_names_native_currency(c, book, kind, phone):
    broker, asset = book
    app = create_app(c)
    if phone:
        @app.middleware('http')
        async def phone_request(request, call_next):
            request.state.phone = True
            return await call_next(request)
    html = TestClient(app).get(f'/investments/new?kind={kind}&account={broker.id}&asset={asset.id}').text
    metadata = json.loads(re.search(r"data-trade-currency='(.*?)'", html).group(1))
    assert metadata['currency'] == 'USD'
    assert all(label.endswith('(USD)') for label in metadata['labels'].values())
    if kind == 'bonus_or_split':
        assert metadata['exchange'] == ''
    else:
        assert '1 USD = 50 EGP' in metadata['exchange']
    assert 'Amount (EGP)' not in html and 'Cost (EGP)' not in html


def test_label_selection_date_and_per_share_basis(c, book):
    broker, asset = book
    client = TestClient(create_app(c))
    query = {'asset_id': asset.id, 'account_id': broker.id, 'date': '2026-09-01', 'kind': 'dividend', 'dividend_basis': 'per_share'}
    data = client.get('/investments/entry-currency', params=query).json()
    assert data['labels']['amount'] == 'Amount per unit (USD)'
    c.fx.save('USD', '2026-09-02', '52')
    assert '52 EGP' in client.get('/investments/entry-currency', params=query | {'date': '2026-09-02'}).json()['exchange']
    native = c.assets.create_investment('Pound fund', 'FUND.EQUITY', 'EGPTEST')
    data = client.get('/investments/entry-currency', params=query | {'asset_id': native.id}).json()
    assert data['currency'] == 'EGP' and data['exchange'] == ''


def test_buy_and_edit_labels_agree_with_cash(c, book):
    broker, asset = book
    client = TestClient(create_app(c), follow_redirects=False)
    r = client.post('/investments/new?kind=buy', data={'date':'2026-09-02', 'account_id':broker.id,
                      'asset_id':asset.id, 'quantity':'10', 'total':'100', 'fees':'0'})
    assert r.status_code == 303
    assert c.reporting.account_balance(broker.id, '2026-09-02') == Decimal('900')
    holding = c.investments.portfolio('2026-09-02', broker.id).open[0]
    assert holding.cost_basis == Decimal('5000')
    txn = c.db.scalar("SELECT id FROM transactions WHERE type='BUY'")
    html = client.get(f'/investments/{txn}/edit').text
    assert 'Amount (USD)' in html and 'Price per unit (USD)' in html


def test_pc_popup_currency_switch_and_save(c, book):
    from playwright.sync_api import sync_playwright, expect
    from tests.browser_support import require_chromium
    from lightning.runtime.http import Host
    broker, asset = book
    native = c.assets.create_investment('Pound fund', 'FUND.EQUITY', 'EGPFORM')
    c.investments.add_holding(broker.id, asset.id, '10', '100', '2026-09-01')
    host = Host(lambda cfg: create_app(c)).start()
    try:
        with sync_playwright() as pw:
            with pw.chromium.launch(executable_path=require_chromium(), args=['--no-sandbox']) as browser:
                page = browser.new_page(viewport={'width':1366, 'height':768})
                page.goto(host.origin + f'/investments/holding/{asset.id}?account={broker.id}&date=2026-09-02')
                page.get_by_role('link', name='Buy more', exact=True).click()
                form = page.locator('#app-popup form.investment-ownership-form')
                expect(form.locator('label[for=total]')).to_have_text('Amount (USD)')
                form.get_by_role('combobox', name='Investment', exact=True).fill('Pound fund')
                page.get_by_role('option', name='Pound fund', exact=True).click()
                expect(form.locator('label[for=total]')).to_have_text('Amount (EGP)')
                form.get_by_role('combobox', name='Investment', exact=True).fill('Dollar fund')
                page.get_by_role('option', name='Dollar fund', exact=True).click()
                expect(form.locator('label[for=total]')).to_have_text('Amount (USD)')
                form.locator('[name=date]').fill('2026-09-02')
                form.locator('[name=date]').dispatch_event('change')
                expect(form.locator('[data-trade-exchange]')).to_contain_text('50 EGP')
                form.locator('[name=quantity]').fill('10')
                form.locator('[name=total]').fill('100')
                with page.expect_response(lambda r: r.request.method == 'POST' and '/investments/new' in r.url):
                    form.get_by_role('button', name='Record buy', exact=True).click()
                expect(page.locator('#app-popup')).not_to_be_visible()
                assert c.reporting.account_balance(broker.id, '2026-09-02') == Decimal('900')
    finally:
        host.stop()


def test_validation_and_arabic_keep_the_currency(c, book):
    broker, asset = book
    client = TestClient(create_app(c))
    response = client.post('/investments/new?kind=buy', data={'date':'2026-09-02', 'account_id':broker.id,
                          'asset_id':asset.id, 'quantity':'10', 'total':'invalid'})
    assert response.status_code == 400 and 'Amount (USD)' in response.text
    c.settings.set('locale', 'ar')
    labels = client.get('/investments/entry-currency', params={'asset_id':asset.id}).json()['labels']
    assert labels['total'] == 'المبلغ (USD)'
    native = c.assets.create_investment('Local fund', 'FUND.EQUITY', 'LOCALFORM')
    labels = client.get('/investments/entry-currency', params={'asset_id':native.id}).json()['labels']
    assert labels['total'] == 'المبلغ (ج.م)'
