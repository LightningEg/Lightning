"""Smarter planning keeps native payments and base totals consistent through the UI."""
from datetime import date
from decimal import Decimal
import re

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


def test_goal_review_and_plan_note_work_without_an_explicit_budget(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-09-30')
    account, cats = setup
    c.transactions.record_inflow('2026-09-15', account['cib'].id, '10000', cats['EXP.WORK.SALARY'].id)
    assert isinstance(c.health.goal_reach('2026-09'), list)
    assert isinstance(c.health.plan_note('2026-09'), str)
    client = TestClient(create_app(c))
    for path in ('/', '/review', '/plan', '/financial-health'):
        assert client.get(path).status_code == 200, path


def _foreign_plan(c, kind='BILL', **kw):
    c.currencies.register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    account = c.account_flows.open_account('Dollars', 'BANK', '2026-09-01', '1000', currency='USD')
    category = c.categories.get_by_code('EXP.WORK.SALARY' if kind == 'INCOME' else 'EXP.WORK.SOFTWARE')
    item = c.planning.create(kind=kind, name='Cloud service', amount='10', frequency='MONTHLY',
                             start_date='2026-10-05', account_id=str(account.id),
                             category_id=str(category.id), **kw)
    return account, category, c.planning.get(item)


def test_foreign_bill_totals_and_posting_use_the_correct_currencies(c, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-06')
    account, category, item = _foreign_plan(c)
    assert c.planning.what_you_owe(date(2026, 10, 6)).bills_due == Decimal('500')
    assert c.planning.budget_fill_schedule('2026-10')[category.id]['amount'] == Decimal('500')
    assert c.health.bills_a_month(date(2026, 10, 6)) == Decimal('500')
    txn = c.transactions.record_outflow('2026-10-05', account.id, '10', category.id)
    assert c.planning.match_payments(date(2026, 10, 6)) == 1
    payment = c.planning.payments(item, '2026-10-31', date(2026, 10, 6))[0]
    assert payment.transaction_id == txn.id
    assert payment.paid_amount == Decimal('10')
    assert c.planning.what_you_owe(date(2026, 10, 6)).bills_due == 0
    assert c.reporting.account_balance(account.id) == Decimal('990')


def test_forecast_converts_upcoming_native_bills_without_using_future_fx(c, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-09-30')
    account, _, item = _foreign_plan(c)
    # The database can contain later rates, but a historical forecast cannot see them.
    c.db.execute("INSERT INTO fx_rates(base,quote,date,rate_e6,source,created_at) VALUES ('USD','EGP','2026-10-01',90000000,'MANUAL','2026-09-30T12:00:00')")
    assert c.planning.amount_in_base(item, Decimal('10'), date(2026, 10, 5)) == Decimal('500')
    forecast = c.forecaster.forecast(date(2026, 9, 30))
    assert next(row for row in forecast.months if row.month == '2026-10').commitments == Decimal('500')


def test_missing_scheduled_fx_gives_a_recoverable_setup_page(c, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-09-30')
    _, _, item = _foreign_plan(c)
    c.db.execute("DELETE FROM fx_rates WHERE base='USD'")
    with pytest.raises(ValidationError, match='exchange rate'):
        c.planning.amount_in_base(item, item.amount, date(2026, 9, 30))
    client = TestClient(create_app(c))
    reply = client.get('/plan')
    assert reply.status_code == 422 and 'Add a rate' in reply.text
    assert client.get('/settings?section=currencies&tab=rates').status_code == 200


def test_promotion_preserves_month_end_after_posting_the_form(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2027-02-01')
    accounts, cats = setup
    txn = c.transactions.record_outflow('2027-01-31', accounts['cib'].id, '123.45', cats['EXP.WORK.SOFTWARE'].id)
    client = TestClient(create_app(c))
    source = c.planning.from_transaction(txn.id)
    assert source['values']['start_date'] == '2027-02-28'
    form = client.get(f'/plan/from-transaction/{txn.id}').text
    assert 'name="month_day"' in form
    values = source['values'] | {'past_due': 'due'}
    result = client.post(f'/plan/from-transaction/{txn.id}', data=values, follow_redirects=False)
    assert result.status_code == 303
    item = c.planning.items()[0]
    assert item.month_day == 31
    payments = c.planning.payments(item, '2027-04-30', date(2027, 2, 1))
    assert [p.due_date for p in payments] == ['2027-02-28', '2027-03-31', '2027-04-30']
    assert c.reporting.account_balance(accounts['cib'].id) == Decimal('49876.55')


@pytest.mark.parametrize('window,tolerance', [('0','0'), ('31','25')])
def test_matching_configuration_survives_the_ui(c, setup, window, tolerance):
    accounts, cats = setup
    client = TestClient(create_app(c))
    result = client.post('/plan/items', data={
        'kind': 'BILL', 'name': 'Configured', 'amount': '100', 'frequency': 'MONTHLY',
        'interval_count': '1', 'start_date': '2027-01-05', 'past_due': 'due',
        'account_id': str(accounts['cib'].id), 'category_id': str(cats['EXP.WORK.SOFTWARE'].id),
        'match_window_days': window, 'match_tolerance_pct': tolerance,
    }, follow_redirects=False)
    assert result.status_code == 303
    item = c.planning.items()[0]
    assert (item.match_window_days, item.match_tolerance_pct) == (int(window), int(tolerance))
    assert client.get(f'/plan/items/{item.id}/edit').status_code == 200


@pytest.mark.parametrize('field,value', [('match_window_days','-1'), ('match_window_days','32'),
    ('match_window_days','oops'), ('match_tolerance_pct','26'), ('match_tolerance_pct','oops')])
def test_invalid_matching_limits_are_refused_without_creating_a_plan(c, setup, field, value):
    accounts, cats = setup
    client = TestClient(create_app(c))
    response = client.post('/plan/items', data={
        'kind': 'BILL', 'name': 'Invalid', 'amount': '100', 'frequency': 'MONTHLY',
        'interval_count': '1', 'start_date': '2027-01-01', 'account_id': str(accounts['cib'].id),
        'category_id': str(cats['EXP.WORK.SOFTWARE'].id), field: value,
    })
    assert response.status_code == 400
    assert c.planning.items() == []
