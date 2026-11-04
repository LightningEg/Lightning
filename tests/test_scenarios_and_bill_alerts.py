"""Scenario previews move no money; bill alerts require identity, cadence and robust evidence."""
from datetime import date
from decimal import Decimal as D
import pytest
from fastapi.testclient import TestClient
from lightning.planning.scenarios import compare_scenario
from lightning.ui.web import create_app
from lightning.workflows.bill_alerts import bill_alerts
from lightning.workflows.review import ReviewInbox


def planned(c, account, kind, start, amount='100', party=None, category=None):
    return c.planning.create(name='Salary' if kind == 'INCOME' else 'Subscription', kind=kind, amount=amount,
                             frequency='MONTHLY', start_date=start, account_id=account.id,
                             counterparty_id=party, category_id=category)


def snapshot(c):
    return {table: [tuple(r) for r in c.db.all(f'SELECT * FROM {table} ORDER BY 1')]
            for table in ('transactions','ledger_entries','planned_items','planned_payments','cash_reserves','reserve_allocation_history')}


def test_purchase_and_income_delay_change_exactly_one_occurrence_without_writes(c):
    a = c.account_flows.open_account('Bank','BANK','2026-09-01','100')
    salary = planned(c,a,'INCOME','2026-09-05','1000')
    planned(c,a,'BILL','2026-09-06','500')
    before = snapshot(c)
    result = compare_scenario(c.forecaster,date(2026,9,1),date(2026,9,30),income=f'{salary}:2026-09-05',
                              delay='5',purchase='200',purchase_date='2026-09-03',account_id=str(a.id))
    assert result.baseline_low.balance == 100
    assert result.scenario_low.balance == -600
    assert result.scenario.first_shortfall.date == '2026-09-03'
    assert result.baseline.balances[-1].balance == 600
    assert result.scenario.balances[-1].balance == 400  # delay changes timing, not total income
    assert snapshot(c) == before


def test_overdue_income_is_excluded_until_explicitly_rescheduled_and_bill_override_replaces(c):
    a = c.account_flows.open_account('Bank','BANK','2026-09-01','100')
    salary = planned(c,a,'INCOME','2026-09-01','1000')
    bill = planned(c,a,'BILL','2026-09-15','100')
    result = compare_scenario(c.forecaster,date(2026,9,3),date(2026,9,30),income=f'{salary}:2026-09-01',delay='5',
                              bill=f'{bill}:2026-09-15',bill_amount='200')
    assert result.baseline.balances[-1].balance == 0
    assert result.scenario.balances[-1].balance == 900


def test_insufficient_history_does_not_invent_salary_or_spending(c):
    a = c.account_flows.open_account('Bank','BANK','2026-09-01','100')
    result = compare_scenario(c.forecaster,date(2026,9,1),date(2026,9,30))
    assert result.baseline_low.balance == result.scenario_low.balance == 100
    assert not result.assumptions


def fixture(c, amounts, *, utilities=False, months=None):
    a = c.account_flows.open_account('Bank','BANK','2026-01-01','10000')
    party = c.counterparties.create('Electricity' if utilities else 'Streaming')
    cat = c.categories.get_by_code('EXP.PERSONAL.UTILITIES' if utilities else 'EXP.PERSONAL.ENTERTAINMENT')
    planned(c,a,'BILL' if utilities else 'SUBSCRIPTION','2026-01-05',party=party,category=cat.id)
    txns = []
    for i, amount in enumerate(amounts):
        month = (months or list(range(1,len(amounts)+1)))[i]
        txns.append(c.transactions.record_outflow(f'2026-{month:02}-05',a.id,str(amount),cat.id,counterparty=c.counterparties.get(party)['name']))
    return a, party, cat, txns


@pytest.mark.parametrize('amounts,expected', [([100,100,100,140],['drift']),([100,100,100,110],[]),
                                             ([100,160,80,180],[]),([100,100,180],[])])
def test_fixed_bill_drift_labelled_positive_and_negative_fixtures(c, amounts, expected):
    fixture(c,amounts)
    alerts = bill_alerts(c,date(2026,len(amounts),20))
    assert [a['label'] for a in alerts] == ['Bill amount changed' for _ in expected]


def test_repeated_subscription_is_reviewable_durable_and_never_deleted(c):
    a, party, cat, txns = fixture(c,[100,100,100,100])
    c.transactions.record_outflow('2026-04-06',a.id,'100',cat.id,counterparty='Streaming')
    alerts = bill_alerts(c,date(2026,4,20))
    assert len(alerts) == 1 and alerts[0]['label'] == 'Possible repeated bill charge'
    before = [tuple(r) for r in c.db.all('SELECT * FROM ledger_entries')]
    inbox = ReviewInbox(c)
    item = next(i for i in inbox.items(date(2026,4,20)) if i['href'] == alerts[0]['href'])
    inbox.decide(item['review_id'],'snoozed',date(2026,4,20),'2026-04-25')
    assert item['review_id'] not in {i['review_id'] for i in ReviewInbox(c).items(date(2026,4,24))}
    assert item['review_id'] in {i['review_id'] for i in ReviewInbox(c).items(date(2026,4,25))}
    inbox.decide(item['review_id'],'reviewed',date(2026,4,25))
    assert item['review_id'] not in {i['review_id'] for i in ReviewInbox(c).items(date(2026,4,25))}
    assert [tuple(r) for r in c.db.all('SELECT * FROM ledger_entries')] == before


def test_utilities_and_refunds_suppress_ordinary_fluctuation_and_duplicate_alerts(c):
    a, party, cat, txns = fixture(c,[100,120,90,110,100,95,140],utilities=True)
    assert not bill_alerts(c,date(2026,7,20))
    c.transactions.record_inflow('2026-07-06',a.id,'140',cat.id,counterparty='Electricity')
    assert not bill_alerts(c,date(2026,7,20))


@pytest.mark.parametrize('phone',[False,True])
@pytest.mark.parametrize('locale',['en','ar'])
def test_scenario_get_and_alert_pages_work_without_preview_writes(c,phone,locale,monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY','2026-04-20')
    a, party, cat, txns = fixture(c,[100,100,100,140])
    c.settings.set('locale',locale)
    app = create_app(c)
    @app.middleware('http')
    async def frame(request,call_next):
        request.state.phone=phone
        return await call_next(request)
    before = snapshot(c)
    with TestClient(app) as client:
        response=client.get('/plan/scenarios',params={'purchase':'200','purchase_date':'2026-04-21','account_id':a.id})
        assert response.status_code == 200
        alert=bill_alerts(c,date(2026,4,20))[0]
        response=client.get(alert['href'])
        assert response.status_code == 200 and txns[-1].ref in response.text
        if locale == 'ar':
            assert 'Bill amount changed' not in response.text
    assert snapshot(c) == before
