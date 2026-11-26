"""Savings presentation clamps only the picture, never the financial definition."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.investments.report import saved_and_invested, investing_rate
from lightning.reporting.service import CashFlow
from lightning.ui.web import create_app


@pytest.mark.parametrize('income,spend,added,state,saved,excess', [
    ('100','60','150','saved',40,0), ('100','125','0','overspent',0,25),
    ('100','350','0','overspent',0,100), ('100','100','0','saved',0,0),
    ('0','25','0','overspent',0,100), ('0','0','0','empty',0,0),
    ('100','66.5','100','saved',34,0), ('100','67.5','100','saved',32,0),
])
def test_savings_picture(income, spend, added, state, saved, excess):
    flow = CashFlow('', '', D(income), D(0), D(0), D(spend), D(0), D(0), D(0))
    w = saved_and_invested(flow, D(added))
    assert flow.net == D(income) - D(spend)
    assert w['saved'] == flow.savings_rate
    assert w['invested'] == investing_rate(D(added), flow.net)
    bar = w['bar']
    assert bar['state'] == state
    assert len(bar['cells']) == 100
    assert bar['cells'].count('kept') == saved
    assert bar['cells'].count('overspent') == excess
    assert 'invested' not in bar['cells']
    assert bar['saved_amount'] >= 0 and bar['overspent_amount'] >= 0
    assert bar['displayed_rate'] is None if not D(income) else bar['displayed_rate'] >= 0


@pytest.mark.parametrize('income,spend', [('100','60'), ('100','125'), ('100','350'), ('100','100'), ('0','25'), ('0','0')])
# The waffle lives behind the Overview's Savings rate (owner 2026-10-19; moved off Investments with guideline 3.33).
@pytest.mark.parametrize('path', ['/'])
def test_shared_savings_view(c, income, spend, path):
    import re
    account = c.account_flows.open_account('Daily', 'BANK', '2026-09-01', '1000')
    if path == '/investments':
        broker = c.account_flows.open_account('Broker', 'BROKERAGE', '2026-09-01', '0')
        c.transactions.record_transfer('2026-09-01', account.id, broker.id, '10')
        asset = c.assets.create_investment('Test stock', 'STOCK', 'TEST')
        c.investments.buy_total('2026-09-01', broker.id, asset.id, '1', '10')
    if D(income):
        c.transactions.record_inflow('2026-09-02', account.id, income, c.categories.get_by_code('EXP.WORK.SALARY').id)
    if D(spend):
        c.transactions.record_outflow('2026-09-03', account.id, spend, c.categories.get_by_code('EXP.PERSONAL.FOOD').id)
    html = TestClient(create_app(c)).get(path+'?period=month&month=2026-09').text
    grid = re.search(r'<span class="waffle inv-waffle"[^>]*>(.*?)</span>', html, re.S)
    note = re.search(r'<small class="muted inv-saved-note">(.*?)</small>', html, re.S)
    if not D(income) and not D(spend):
        assert grid is None
        return
    assert len(re.findall(r'<i class=', grid[1])) == 100
    assert 'invested' not in grid[1]
    assert 'earlier savings' not in note[1]
    key = re.search(r'<span class="saved-key">(.*?)</span></span>', html, re.S)[1]
    assert 'Invested' not in key and 'Kept' not in key
    if D(spend) > D(income):
        assert 'Overspent' in key and '-' not in re.sub(r'<[^>]+>', '', key)
    if D(income) and D(spend) > 2 * D(income):
        assert 'The grid stops at 100% of income.' in note[1]
    if not D(income):
        figures = re.search(r'<span class="inv-saved-figures">(.*?)</em>', html, re.S)[1]
        assert '%' not in figures
        assert '1%' not in note[1]


@pytest.mark.parametrize("income", ["0", "1000"])
def test_overview_shows_net_refunds_without_a_negative_bar_or_an_implied_savings_rate(c, setup, income):
    bank = setup[0]["cib"].id
    if D(income):
        c.transactions.record_inflow("2026-09-01", bank, income, setup[1]["EXP.WORK.SALARY"].id)
    c.transactions.record_refund("2026-09-03", bank, "200", setup[1]["EXP.PERSONAL.FOOD"].id)
    page = TestClient(create_app(c)).get("/?month=2026-09").text
    assert "Refunds were more than your spending" in page
    assert 'class="net-flow-bars"' not in page and 'class="waffle inv-waffle"' not in page
    assert 'id="savings-squares"' in page
    assert "+200" in page.split('id="flow-heading"', 1)[1]


def test_monthly_savings_spark_restarts_after_a_month_with_net_refunds(c, setup):
    from datetime import date
    from lightning.ui.visuals import savings_rates

    account = setup[0]["cib"].id
    salary, food = setup[1]["EXP.WORK.SALARY"].id, setup[1]["EXP.PERSONAL.FOOD"].id
    for month in ("09", "10", "11"):
        c.transactions.record_inflow(f"2026-{month}-01", account, "1000", salary)
    c.transactions.record_refund("2026-10-05", account, "200", food)
    c.transactions.record_outflow("2026-11-05", account, "300", food)
    assert savings_rates(c, date(2026, 11, 15)) == [D(70)]


def test_returned_salary_explains_negative_money_in(c, setup):
    bank = setup[0]["cib"].id
    c.transactions.record_outflow("2026-09-01", bank, "1000", setup[1]["EXP.WORK.SALARY"].id)
    c.transactions.record_outflow("2026-09-02", bank, "200", setup[1]["EXP.PERSONAL.FOOD"].id)
    page = TestClient(create_app(c)).get("/?month=2026-09").text
    assert "More income was returned than received" in page
    assert 'class="net-flow-bars"' not in page and 'class="waffle inv-waffle"' not in page
