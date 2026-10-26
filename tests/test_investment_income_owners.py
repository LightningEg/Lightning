"""5L: distributions and realized gains retain the owner of the actual ledger activity."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from starlette.responses import HTMLResponse

from lightning.investments.report import results_by_asset
from lightning.ui.web import create_app


@pytest.fixture
def mixed(c):
    broker=c.account_flows.open_account('Mixed broker','BROKERAGE','2026-09-01','1000')
    owner=c.counterparties.create('Saved person')
    salary=c.categories.get_by_code('EXP.WORK.SALARY').id
    c.transactions.record_inflow('2026-09-01',broker.id,'1000',salary,owner_id=owner)
    asset=c.assets.create_investment('Shared share','STOCK','OWNERTEST')
    c.investments.buy('2026-09-02',broker.id,asset.id,'1','10')
    c.investments.buy('2026-09-02',broker.id,asset.id,'9','10',owner_id=owner)
    c.assets.set_price(asset.id,'2026-09-02','10')
    return broker,owner,asset


def position(c):
    return c.investments.portfolio('2026-09-30').positions[0]


def period_result(c, asset, start='2026-09-01'):
    _,rows=results_by_asset(c.investments,c.money_from_others,c.reporting,start,'2026-09-30')
    return rows.get(asset.id,{}).get('result',D(0))


@pytest.mark.parametrize('recipient,expected', [('me',D(90)),('other',D(0))])
def test_only_actual_owner_receives_the_dividend_and_withholding(c,mixed,recipient,expected):
    broker,owner,asset=mixed
    before=c.reporting.owned_account_value(broker.id,'2026-09-02')
    c.investments.dividend('2026-09-03',broker.id,asset.id,'100',owner_id=owner if recipient=='other' else None,tax='10')
    p=position(c)
    assert p.net_dividends==D(90)  # the gross account model still includes both owners
    assert p.owned_net_dividends==expected
    assert p.owned_result(p.owned_quantity,D(10),p.owned_cost_basis)['gain']==expected
    assert period_result(c,asset)==expected
    assert c.reporting.owned_account_value(broker.id,'2026-09-30')-before==expected


def test_later_purchases_and_other_owners_exit_do_not_reallocate_prior_income(c,mixed):
    broker,owner,asset=mixed
    c.investments.dividend('2026-09-03',broker.id,asset.id,'100',tax='10')
    c.investments.dividend('2026-09-04',broker.id,asset.id,'200',owner_id=owner,tax='20')
    c.investments.buy('2026-09-05',broker.id,asset.id,'9','10')
    c.investments.sell('2026-09-06',broker.id,asset.id,'9','10',owner_id=owner)
    p=position(c)
    assert p.owned_quantity==p.quantity==D(10)
    assert p.has_other_owners
    assert p.owned_net_dividends==D(90)
    assert p.owned_result(D(10),p.value,p.owned_cost_basis)['gain']==D(90)
    assert period_result(c,asset)==D(90)
    assert period_result(c,asset,'2026-09-05')==0


def test_closed_position_retains_only_own_realized_gain_and_income(c,mixed):
    broker,owner,asset=mixed
    c.investments.dividend('2026-09-03',broker.id,asset.id,'50',tax='5')
    c.investments.dividend('2026-09-03',broker.id,asset.id,'100',owner_id=owner)
    c.investments.sell('2026-09-04',broker.id,asset.id,'1','12')
    c.investments.sell('2026-09-04',broker.id,asset.id,'9','20',owner_id=owner)
    p=position(c)
    assert not p.is_open
    assert p.owned_result(D(0),D(0),D(0))['gain']==D(47)
    assert period_result(c,asset)==D(47)


def test_holding_and_overview_views_read_owned_distributions(c,mixed,monkeypatch):
    from lightning.ui.routes import investments as routes
    broker,owner,asset=mixed
    c.investments.dividend('2026-09-03',broker.id,asset.id,'100',owner_id=owner,tax='10')
    context={}
    def capture(request,template,**values):
        context.clear(); context.update(values)
        return HTMLResponse('ok')
    monkeypatch.setattr(routes,'render',capture)
    with TestClient(create_app(c)) as client:
        response=client.get(f'/investments/holding/{asset.id}?account={broker.id}&date=2026-09-30&start=2026-09-01')
        assert response.status_code==200
        assert context['h'].dividends==context['h'].dividend_tax==context['total_return']==0
        response=client.get('/investments?period=month&month=2026-09')
        assert response.status_code==200
        assert context['period_dividends']==0
        assert all(row['dividends']==0 for _,row in context['asset_class_rows'])
