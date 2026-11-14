"""BT-12AO: register amounts derive the right units before recording cash and gains."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


DAY = '2026-09-02'


@pytest.fixture
def book(c):
    broker = c.account_flows.open_account('Sale broker', 'BROKERAGE', '2026-09-01', '1000')
    asset = c.assets.create_investment('Amount fund', 'FUND.EQUITY', 'AMOUNT')
    c.investments.buy('2026-09-01', broker.id, asset.id, '20', '10')
    c.assets.set_price(asset.id, DAY, '10')
    client = TestClient(create_app(c), follow_redirects=False)
    form = {'date': DAY, 'instrument_key': f'asset:{asset.id}', 'trade_action': 'sell',
            'units': '', 'unit_price': '10', 'total': '100', 'fees': '10', 'price_basis': 'unit_price'}
    return broker, asset, client, form


def post(book, **changes):
    broker, _, client, form = book
    return client.post(f'/accounts/{broker.id}/investment-entry', data=form | changes)


@pytest.mark.parametrize('action,included,units,cash', [
    ('sell', '', '11', '900'), ('sell', '0', '10', '890'),
    ('buy', '', '9', '700'), ('buy', '0', '10', '690'),
])
def test_amount_only_trade_moves_units_cash_and_cost_together(c, book, action, included, units, cash):
    broker, asset, _, _ = book
    response = post(book, trade_action=action, fees_included=included)
    assert response.status_code == 303, response.text[:500]
    h = c.investments.portfolio(DAY, broker.id).open[0]
    delta = D(units) * (-1 if action == 'sell' else 1)
    assert h.quantity == D('20') + delta
    assert c.reporting.account_balance(broker.id, DAY) == D(cash)
    if action == 'sell':
        assert h.cost_basis == h.quantity * 10
        assert h.realized == -D('10')
    else:
        assert h.cost_basis == D('200') + D('800') - D(cash)
    assert not c.db.all("SELECT transaction_id FROM ledger_entries WHERE effect='INTERNAL' "
                          'GROUP BY transaction_id HAVING SUM(amount_base_e6)<>0')


@pytest.mark.parametrize('action,included,cash', [
    ('sell', '', '890'), ('sell', '0', '890'), ('buy', '', '690'), ('buy', '0', '690'),
])
def test_explicit_units_and_unit_price_keep_their_existing_meaning(c, book, action, included, cash):
    broker, _, _, _ = book
    response = post(book, trade_action=action, units='10', total='', fees_included=included)
    assert response.status_code == 303, response.text[:500]
    h = c.investments.portfolio(DAY, broker.id).open[0]
    assert h.quantity == (D('10') if action == 'sell' else D('30'))
    assert c.reporting.account_balance(broker.id, DAY) == D(cash)


@pytest.mark.parametrize('action,included,cash', [
    ('sell', '', '900'), ('sell', '0', '890'), ('buy', '', '700'), ('buy', '0', '690'),
])
def test_explicit_units_and_total_are_not_rederived(c, book, action, included, cash):
    broker, _, _, _ = book
    response = post(book, trade_action=action, units='10', price_basis='total', fees_included=included)
    assert response.status_code == 303, response.text[:500]
    h = c.investments.portfolio(DAY, broker.id).open[0]
    assert h.quantity == (D('10') if action == 'sell' else D('30'))
    assert c.reporting.account_balance(broker.id, DAY) == D(cash)


@pytest.mark.parametrize('places,units', [(0, '7'), (2, '7.33'), (4, '7.3333'), (6, '7.333333')])
def test_derived_units_follow_the_asset_precision(c, book, places, units):
    broker, asset, _, _ = book
    c.db.execute('UPDATE financial_assets SET quantity_decimals=? WHERE id=?', (places, asset.id))
    response = post(book, total='20', fees='2', unit_price='3')
    assert response.status_code == 303, response.text[:500]
    assert c.investments.portfolio(DAY, broker.id).open[0].quantity == D('20') - D(units)
    assert c.reporting.account_balance(broker.id, DAY) == D('820')


def test_amount_only_sale_can_use_the_dated_saved_price(c, book):
    broker, asset, _, _ = book
    c.assets.set_price(asset.id, '2026-09-03', '20')  # a future price must not change this sale
    assert post(book, unit_price='').status_code == 303
    assert c.investments.portfolio(DAY, broker.id).open[0].quantity == D('9')
    assert c.reporting.account_balance(broker.id, DAY) == D('900')


def test_fee_boundary_oversell_is_refused_without_a_partial_save(c, book):
    broker, _, _, _ = book
    count = c.db.scalar('SELECT COUNT(*) FROM transactions')
    response = post(book, total='195')  # 19.5 net-price units, but 20.5 units including the fee
    assert response.status_code == 400
    assert c.db.scalar('SELECT COUNT(*) FROM transactions') == count
    assert c.investments.portfolio(DAY, broker.id).open[0].quantity == D('20')
    assert c.reporting.account_balance(broker.id, DAY) == D('800')


def test_amount_only_full_sale_and_resubmission_leave_no_phantom_units(c, book):
    broker, _, _, _ = book
    assert post(book, total='190', submission='a' * 32).status_code == 303
    count = c.db.scalar('SELECT COUNT(*) FROM transactions')
    assert post(book, total='190', submission='a' * 32).status_code == 303
    assert c.db.scalar('SELECT COUNT(*) FROM transactions') == count
    h = c.investments.portfolio(DAY, broker.id).positions[0]
    assert h.quantity == 0 and h.cost_basis == 0 and h.realized == -10
    assert c.reporting.account_balance(broker.id, DAY) == D('990')


@pytest.mark.parametrize('changes', [{'total': '0'}, {'total': '-100'}, {'fees': '-10'},
                                    {'unit_price': '0'}, {'unit_price': '-10'}, {'total': '100.001'}])
def test_invalid_amount_only_sales_leave_the_ledger_unchanged(c, book, changes):
    broker, _, _, _ = book
    count = c.db.scalar('SELECT COUNT(*) FROM transactions')
    assert post(book, **changes).status_code == 400
    assert c.db.scalar('SELECT COUNT(*) FROM transactions') == count
    assert c.investments.portfolio(DAY, broker.id).open[0].quantity == 20
    assert c.reporting.account_balance(broker.id, DAY) == 800


def test_foreign_amount_only_sale_keeps_native_cash_and_base_gains(c):
    c.currencies.register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    broker = c.account_flows.open_account('Foreign broker', 'BROKERAGE', '2026-09-01', '1000', currency='USD')
    asset = c.assets.create_investment('Foreign fund', 'FUND.EQUITY', 'FOREIGN', currency='USD')
    c.investments.buy('2026-09-01', broker.id, asset.id, '20', '10')
    client = TestClient(create_app(c), follow_redirects=False)
    response = client.post(f'/accounts/{broker.id}/investment-entry', data={
        'date': DAY, 'instrument_key': f'asset:{asset.id}', 'trade_action': 'sell',
        'unit_price': '10', 'total': '100', 'fees': '10'})
    assert response.status_code == 303, response.text[:500]
    h = c.investments.portfolio(DAY, broker.id).open[0]
    assert h.quantity == 9 and h.cost_basis == 4500 and h.realized == -500
    assert c.reporting.account_balance(broker.id, DAY) == 900


def test_desktop_amount_only_sale_records_eleven_units(c, book, tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from tests.browser_support import require_chromium
    from lightning.runtime.http import Host

    broker, _, _, _ = book
    host = Host(lambda cfg: create_app(c)).start()
    try:
        with sync_playwright() as pw:
            with pw.chromium.launch(executable_path=require_chromium(), args=['--no-sandbox']) as browser:
                page = browser.new_page(viewport={'width': 1366, 'height': 768})
                page.goto(host.origin + f'/accounts/{broker.id}')
                form = page.locator('.investment-entry-form')
                form.get_by_role('button', name='Sell', exact=True).click()
                form.get_by_role('searchbox', name='Investment', exact=True).fill('Amount fund')
                page.get_by_role('option', name='Amount fund', exact=False).click()
                form.locator('[name=date]').fill(DAY)
                form.locator('[name=unit_price]').fill('10')
                form.locator('[name=total]').fill('100')
                form.locator('[name=fees]').fill('10')
                expect(form.locator('[name=units]')).to_have_value('')
                form.scroll_into_view_if_needed()
                page.screenshot(path=str(tmp_path / 'amount-only-sale-desktop.png'))
                with page.expect_response(lambda r: r.request.method == 'POST' and '/investment-entry' in r.url) as saved:
                    form.get_by_role('button', name='Add', exact=True).click()
                assert saved.value.status in (200, 303)
                assert c.investments.portfolio(DAY, broker.id).open[0].quantity == 9
                assert c.reporting.account_balance(broker.id, DAY) == 900
    finally:
        host.stop()
