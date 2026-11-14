"""BT-12AN: purchase values and returns use the same dated base currency as cost and the holding headline."""
import re
from dataclasses import replace
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.database.currencies import CurrencyRegistry
from lightning.investments.lots import Lot
from lightning.investments.views import purchase_returns
from lightning.ui.web import create_app


@pytest.fixture
def foreign(c):
    CurrencyRegistry(c.db).register('USD')
    c.fx.save('USD', '2025-12-31', '50')
    broker = c.account_flows.open_account('Dollar broker', 'BROKERAGE', '2025-12-31', '1000', currency='USD')
    asset = c.assets.create_investment('Dollar holding', 'FUND.EQUITY', 'USDLOT', currency='USD')
    c.investments.buy('2025-12-31', broker.id, asset.id, '10', '10')
    return broker, asset


@pytest.mark.parametrize('price,rate,value,percent', [('10','50','5000','0'), ('12','50','6000','20'),
                                                    ('10','55','5500','10'), ('12','55','6600','32')])
def test_price_and_fx_returns_reconcile_to_the_headline(c, foreign, price, rate, value, percent):
    broker, asset = foreign
    c.assets.set_price(asset.id, '2026-12-31', price)
    c.fx.save('USD', '2026-12-31', rate)
    h = c.investments.portfolio('2026-12-31', broker.id).open[0].owned_only()
    rows, _ = purchase_returns(h, '2026-12-31')
    assert h.cost_basis == D('5000') and h.value == D(value)
    assert sum(row['value'] for row in rows) == h.value
    assert sum(row['gain'] for row in rows) == h.unrealized
    assert rows[0]['roi'] == D(percent)
    assert rows[0]['cagr'] == D(percent)  # exactly 365 days


def test_missing_fx_does_not_turn_the_native_quote_into_a_base_value(c, foreign):
    broker, asset = foreign
    c.assets.set_price(asset.id, '2026-12-31', '12')
    h = c.investments.portfolio('2026-12-31', broker.id).open[0].owned_only()
    assert h.price == D('12') and h.value is None
    rows, _ = purchase_returns(h, '2026-12-31')
    assert all(rows[0][key] is None for key in ('value', 'gain', 'roi', 'cagr'))


def test_custody_and_fractional_lots_keep_the_owned_value_exact(c, foreign):
    broker, _ = foreign
    h = c.investments.portfolio('2025-12-31', broker.id).open[0]
    h = replace(h, quantity=D('4'), value=D('1.000001'), owned_quantity=D('3'),
                owned_cost_basis=D('3'), lots=[Lot('2025-12-31', D('1'), D('1')) for _ in range(3)]
                + [Lot('2025-12-31', D('1'), D('1'), owner_id=99)])
    rows, _ = purchase_returns(h, '2026-12-31')
    own_rows, _ = purchase_returns(h.owned_only(), '2026-12-31')
    assert len(rows) == 3
    assert sum(row['value'] for row in rows) == h.owned_only().value
    assert rows == own_rows
    assert sum(row['gain'] for row in rows) == h.owned_only().unrealized


def test_partial_and_full_sales_keep_base_currency_gains(c, foreign):
    broker, asset = foreign
    c.fx.save('USD', '2026-12-31', '55')
    c.assets.set_price(asset.id, '2026-12-31', '12')
    c.investments.sell('2026-12-31', broker.id, asset.id, '4', '12')
    h = c.investments.portfolio('2026-12-31', broker.id).open[0].owned_only()
    rows, sold = purchase_returns(h, '2026-12-31')
    assert sum(row['value'] for row in rows) == D('3960')
    assert sum(row['gain'] for row in rows) == D('960')
    assert sold[0]['gain'] == D('640') and sold[0]['roi'] == D('32')
    c.investments.sell('2026-12-31', broker.id, asset.id, '6', '12')
    h = c.investments.portfolio('2026-12-31', broker.id).positions[0].owned_only()
    rows, sold = purchase_returns(h, '2026-12-31')
    assert rows == [] and sum(row['gain'] for row in sold) == D('1600')


def test_zero_value_and_free_lots_have_honest_returns(c, foreign):
    broker, _ = foreign
    h = c.investments.portfolio('2025-12-31', broker.id).open[0].owned_only()
    rows, _ = purchase_returns(replace(h, value=D(0)), '2026-12-31')
    assert rows[0]['value'] == 0 and rows[0]['roi'] == -100 and rows[0]['cagr'] is None
    free = replace(h, lots=[Lot('2025-12-31', D('10'), D(0))])
    rows, _ = purchase_returns(free, '2026-12-31')
    assert rows[0]['roi'] is None and rows[0]['cagr'] is None


def test_pc_purchase_table_matches_the_dated_header(c, foreign):
    broker, asset = foreign
    c.fx.save('USD', '2026-12-31', '50')
    c.assets.set_price(asset.id, '2026-12-31', '10')
    html = TestClient(create_app(c)).get(f'/investments/holding/{asset.id}?account={broker.id}&date=2026-12-31').text
    table = html.split('Each purchase', 1)[1].split('<tbody>', 1)[1].split('</tbody>', 1)[0]
    cells = [re.sub('<[^>]+>', '', td).strip() for td in re.findall(r'<td[^>]*>(.*?)</td>', table, re.S)]
    assert cells[2:4] == ['5,000', '5,000']
    assert cells[4:] == ['0.0', '0.0']


def test_base_currency_and_short_returns_stay_plain(c):
    broker = c.account_flows.open_account('Local broker', 'BROKERAGE', '2026-12-01', '10000')
    asset = c.assets.create_investment('Local fund', 'FUND.EQUITY', 'LOCALLOT')
    c.investments.buy('2026-12-01', broker.id, asset.id, '100', '10')
    c.assets.set_price(asset.id, '2026-12-31', '12')
    h = c.investments.portfolio('2026-12-31', broker.id).open[0].owned_only()
    rows, _ = purchase_returns(h, '2026-12-31')
    assert rows[0]['value'] == D('1200') and rows[0]['roi'] == D('20')
    assert rows[0]['cagr'] is None


def test_desktop_purchase_value_and_return(c, foreign, tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from tests.browser_support import require_chromium
    from lightning.runtime.http import Host
    broker, asset = foreign
    c.fx.save('USD', '2026-12-31', '50')
    c.assets.set_price(asset.id, '2026-12-31', '10')
    host = Host(lambda cfg: create_app(c)).start()
    try:
        with sync_playwright() as pw:
            with pw.chromium.launch(executable_path=require_chromium(), args=['--no-sandbox']) as browser:
                page = browser.new_page(viewport={'width':1366, 'height':768})
                page.goto(host.origin + f'/investments/holding/{asset.id}?account={broker.id}&date=2026-12-31')
                expect(page.locator('.stat-tile-value').first).to_contain_text('5,000')
                table = page.locator('.journey-table').filter(has=page.get_by_role('columnheader', name='Value', exact=True))
                cells = table.locator('tbody tr').first.locator('td')
                expect(cells.nth(2)).to_have_text('5,000')
                expect(cells.nth(3)).to_have_text('5,000')
                expect(cells.nth(4)).to_have_text('0.0')
                table.scroll_into_view_if_needed()
                page.screenshot(path=str(tmp_path / 'foreign-purchase-returns.png'))
    finally:
        host.stop()


def test_fifo_purchases_keep_their_own_historical_exchange_costs(c, foreign):
    broker, asset = foreign
    c.accounts.set_cost_method(broker.id, 'fifo')
    c.fx.save('USD', '2026-06-30', '60')
    c.investments.buy('2026-06-30', broker.id, asset.id, '10', '10')
    c.assets.set_price(asset.id, '2026-12-31', '10')
    c.fx.save('USD', '2026-12-31', '55')
    h = c.investments.portfolio('2026-12-31', broker.id).open[0].owned_only()
    rows, _ = purchase_returns(h, '2026-12-31')
    assert [row['cost'] for row in rows] == [D('5000'), D('6000')]
    assert [row['value'] for row in rows] == [D('5500'), D('5500')]
    assert [row['gain'] for row in rows] == [D('500'), D('-500')]
    assert rows[0]['roi'] == D('10') and round(rows[1]['roi'], 4) == D('-8.3333')
    assert rows[0]['cagr'] == D('10') and rows[1]['cagr'] is None
    assert sum(row['value'] for row in rows) == h.value == D('11000')
