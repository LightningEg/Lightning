"""BT-12AP: total estimates price the same units displayed, and named gold really changes value."""
import re
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app

DAY = '2026-09-02'


@pytest.fixture
def book(c):
    first = c.account_flows.open_account('First broker', 'BROKERAGE', '2026-09-01', '0')
    second = c.account_flows.open_account('Second broker', 'BROKERAGE', '2026-09-01', '0')
    asset = c.assets.create_investment('Shared fund', 'FUND.EQUITY', 'SCOPE')
    c.investments.add_holding(first.id, asset.id, '91', '910', '2026-09-01')
    c.investments.add_holding(second.id, asset.id, '50', '500', '2026-09-01')
    return first, second, asset, TestClient(create_app(c), follow_redirects=False)


def test_total_value_uses_all_brokers_and_the_displayed_quantity(c, book):
    _, _, asset, client = book
    page = client.get('/investments/prices', params={'date': DAY})
    row = page.text.split(f'id="asset-{asset.id}"', 1)[1].split('</tr>', 1)[0]
    assert '141' in re.sub('<[^>]+>', ' ', row)
    assert 'including units held for others' in page.text
    result = client.post('/investments/prices', data={'date': DAY, f'value_{asset.id}': '1500'})
    assert result.status_code == 303
    positions = [p for p in c.investments.portfolio(DAY).open if p.asset_id == asset.id]
    assert sum(p.quantity for p in positions) == 141
    assert abs(sum(p.value for p in positions) - D('1500')) < D('0.0001')
    assert '/prices?date=2026-09-02' in result.headers['location']
    assert '1,500' in client.get(result.headers['location']).text


def test_custody_units_share_the_price_without_becoming_owned(c, book):
    _, _, asset, client = book
    owner = c.counterparties.ensure_person('Dad')
    custody = c.account_flows.open_account('Custody broker', 'BROKERAGE', '2026-09-01', '0')
    c.investments.add_holding(custody.id, asset.id, '9', '90', '2026-09-01', owner_id=owner)
    assert client.post('/investments/prices', data={'date': DAY, f'value_{asset.id}': '1500'}).status_code == 303
    positions = [p for p in c.investments.portfolio(DAY).open if p.asset_id == asset.id]
    assert sum(p.quantity for p in positions) == 150
    assert sum(p.value for p in positions) == 1500
    assert sum(p.owned_only().value for p in positions) == 1410


@pytest.mark.parametrize('pieces', ['1', '3'])
def test_named_gold_total_uses_the_item_valuation_service(c, pieces):
    account = c.account_flows.open_account('Gold', 'PHYSICAL_ASSET', '2026-09-01', '0')
    ref = c.assets.get_asset_by_code('REF:GLD-24K')
    c.assets.set_price(ref.id, '2026-09-01', '5000')
    asset_id = c.physical_items.create(account.id, 'Named bar', 'Bar', '10', 24, ref.id)
    c.investments.add_holding(account.id, asset_id, pieces, str(D(pieces) * 50000), '2026-09-01')
    client = TestClient(create_app(c), follow_redirects=False)
    html = client.get('/investments/prices', params={'date': DAY}).text
    assert f'name="p_{asset_id}"' not in html and f'name="value_{asset_id}"' in html
    response = client.post('/investments/prices', data={'date': DAY, f'value_{asset_id}': '60000'})
    assert response.status_code == 303
    h = c.investments.portfolio(DAY, account.id).open[0]
    assert h.value == 60000 and h.quantity == D(pieces)
    assert h.cost_basis == D(pieces) * 50000
    assert c.physical_items.valuations(asset_id)[0]['quantity_e6'] == D(pieces) * 1000000
    assert c.assets.price_history(asset_id) == []


@pytest.mark.parametrize('values', [{'value': '-10'}, {'value': '0'}, {'value': 'oops'},
                                   {'value': '100', 'price': '10'}])
def test_bad_totals_do_not_partly_save_other_rows(c, book, values):
    _, _, asset, client = book
    other = c.assets.create_investment('Other fund', 'FUND.EQUITY', 'OTHERSCOPE')
    data = {'date': DAY, f'p_{other.id}': '30', f'value_{asset.id}': values['value']}
    if 'price' in values:
        data[f'p_{asset.id}'] = values['price']
    response = client.post('/investments/prices', data=data)
    assert response.status_code == 303 and '/prices?' in response.headers['location']
    assert c.assets.price_history(other.id) == []
    assert c.assets.price_history(asset.id) == []


def test_unit_price_still_applies_to_every_broker(c, book):
    _, _, asset, client = book
    assert client.post('/investments/prices', data={'date': DAY, f'p_{asset.id}': '12'}).status_code == 303
    assert sum(p.value for p in c.investments.portfolio(DAY).open if p.asset_id == asset.id) == 1692


def test_total_too_small_for_price_precision_is_refused_instead_of_skipped(c, book):
    _, _, asset, client = book
    response = client.post('/investments/prices', data={'date': DAY, f'value_{asset.id}': '0.000001'})
    assert response.status_code == 303
    assert 'too%20small' in response.headers['location']
    assert c.assets.price_history(asset.id) == []


def test_foreign_total_is_in_the_investment_currency(c):
    c.currencies.register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    asset = c.assets.create_investment('Dollar fund', 'FUND.EQUITY', 'DOLLARSCOPE', currency='USD')
    for name, units in [('Dollar one', '10'), ('Dollar two', '20')]:
        broker = c.account_flows.open_account(name, 'BROKERAGE', '2026-09-01', '0', currency='USD')
        c.investments.add_holding(broker.id, asset.id, units, str(D(units) * 10), '2026-09-01')
    client = TestClient(create_app(c), follow_redirects=False)
    assert client.post('/investments/prices', data={'date': DAY, f'value_{asset.id}': '360'}).status_code == 303
    assert sum(p.value for p in c.investments.portfolio(DAY).open if p.asset_id == asset.id) == 18000
    assert '360.00 USD' in client.get('/investments/prices?date=' + DAY).text


def test_physical_unit_price_is_refused_and_bad_total_rolls_back_the_batch(c, book):
    _, _, asset, client = book
    gold = c.account_flows.open_account('Gold', 'PHYSICAL_ASSET', '2026-09-01', '0')
    ref = c.assets.get_asset_by_code('REF:GLD-24K')
    item = c.physical_items.create(gold.id, 'Bar', 'Bar', '10', 24, ref.id)
    c.investments.add_holding(gold.id, item, '1', '50000', '2026-09-01')
    for field in ('p', 'value'):
        response = client.post('/investments/prices', data={'date': DAY, f'p_{asset.id}': '12', f'{field}_{item}': '-10'})
        assert '/prices?' in response.headers['location']
        assert c.assets.price_history(asset.id) == []
        assert c.physical_items.valuations(item) == []


def test_desktop_total_save_shows_the_result_for_the_selected_day(c, book, tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from tests.browser_support import require_chromium
    from lightning.runtime.http import Host
    _, _, asset, _ = book
    gold = c.account_flows.open_account('Gold at home', 'PHYSICAL_ASSET', '2026-09-01', '0')
    ref = c.assets.get_asset_by_code('REF:GLD-24K')
    item = c.physical_items.create(gold.id, 'Desktop gold bar', 'Bar', '10', 24, ref.id)
    c.investments.add_holding(gold.id, item, '1', '50000', '2026-09-01')
    host = Host(lambda cfg: create_app(c)).start()
    try:
        with sync_playwright() as pw:
            with pw.chromium.launch(executable_path=require_chromium(), args=['--no-sandbox']) as browser:
                page = browser.new_page(viewport={'width': 1366, 'height': 768})
                page.goto(host.origin + '/investments/prices?date=' + DAY)
                expect(page.locator(f'#asset-{asset.id}')).to_contain_text('141')
                expect(page.locator(f'[name=p_{item}]')).to_have_count(0)
                form = page.locator('form').filter(has=page.locator(f'[name=value_{asset.id}]'))
                form.locator(f'[name=value_{asset.id}]').fill('1500')
                form.locator(f'[name=value_{item}]').fill('60000')
                form.get_by_role('button', name='Save prices', exact=True).click()
                expect(page).to_have_url(re.compile('/prices\\?date=2026-09-02'))
                expect(page.locator(f'#asset-{asset.id} [data-current-value]')).to_have_text('1,500 EGP')
                expect(page.locator(f'#asset-{item} [data-current-value]')).to_have_text('60,000 EGP')
                expect(page.locator(f'[name=value_{asset.id}]')).to_have_value('')
                page.wait_for_function("!document.getAnimations().some(a => a.playState === 'running')")
                page.screenshot(path=str(tmp_path / 'prices-result-desktop.png'), animations='disabled')
    finally:
        host.stop()
