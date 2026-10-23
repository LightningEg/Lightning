"""2N: optional budget feedback cannot turn a committed save into an error."""
import logging
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


@pytest.fixture
def foreign_bill(c, setup):
    accounts, cats = setup
    c.currencies.register('USD')
    usd = c.account_flows.open_account('USD bank', 'BANK', '2026-09-01', '0', currency='USD')
    c.planning.create(kind='BILL', name='Foreign bill', amount='10', frequency='MONTHLY',
                       start_date='2026-09-05', account_id=str(usd.id),
                       category_id=str(cats['EXP.PERSONAL.FOOD'].id))
    return accounts['cib'], cats['EXP.PERSONAL.FOOD']


def form_for(c, bank, food, flow):
    if flow.startswith('popup'):
        values = dict(kind='out', date='2026-09-10', amount='10', category_id=str(food.id),
                      counterparty='', owner_id='', account_id=str(bank.id), notes='receipt',
                      return_to=f'/accounts/{bank.id}')
        path = f'/accounts/{bank.id}/transaction/new'
    else:
        values = dict(date='2026-09-10', amount='-10', category_choice=str(food.id),
                      account_id=str(bank.id), notes='receipt')
        path = '/transactions/register' if flow.startswith('global') else f'/accounts/{bank.id}/register'
    if flow.endswith('edit'):
        txn = c.transactions.record_outflow('2026-09-10', bank.id, '5', food.id)
        path = f'/transactions/{txn.id}/edit-popup' if flow.startswith('popup') else f'{path}/{txn.id}'
    return path, values


@pytest.mark.parametrize('flow', ['popup-new','register-new','global-new','popup-edit','register-edit','global-edit'])
def test_missing_foreign_bill_fx_keeps_a_successful_save_successful(c, foreign_bill, flow):
    bank, food = foreign_bill
    path, values = form_for(c, bank, food, flow)
    with TestClient(create_app(c)) as client:
        response = client.post(path, data=values, follow_redirects=False)
    assert response.status_code == 303
    message = unquote(response.headers['location'])
    assert 'Saved' in message and 'USD' in message and 'exchange rate' in message
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='OUT'") == 1
    assert c.reporting.account_balance(bank.id) == 49990


def test_unexpected_budget_feedback_error_is_logged_without_inviting_a_retry(c, setup, monkeypatch, caplog):
    bank, food = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    def broken(*args):
        raise RuntimeError('synthetic report failure')
    monkeypatch.setattr(c.budgets, 'month_view', broken)
    path, values = form_for(c, bank, food, 'popup-new')
    with caplog.at_level(logging.ERROR, logger='lightning'), TestClient(create_app(c)) as client:
        response = client.post(path, data=values, follow_redirects=False)
    assert response.status_code == 303
    assert 'Saved' in unquote(response.headers['location'])
    assert 'synthetic report failure' not in unquote(response.headers['location'])
    assert 'Budget feedback' in caplog.text
    assert c.reporting.account_balance(bank.id) == 49990


def test_missing_budget_fx_does_not_hide_a_refused_financial_write(c, foreign_bill):
    bank, food = foreign_bill
    path, values = form_for(c, bank, food, 'popup-new')
    values['amount'] = '60000'
    with TestClient(create_app(c)) as client:
        response = client.post(path, data=values, follow_redirects=False)
    assert response.status_code == 400
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='OUT'") == 0
    assert c.reporting.account_balance(bank.id) == 50000


def test_save_with_missing_budget_fx_keeps_the_posting_and_undo_in_one_action(c, foreign_bill):
    bank, food = foreign_bill
    path, values = form_for(c, bank, food, 'popup-new')
    with TestClient(create_app(c)) as client:
        response = client.post(path, data=values, follow_redirects=False)
        page = client.get(f'/accounts/{bank.id}')
        import re
        group = re.search(r'action="/history/undo".*?name="group_id" value="(\d+)"',page.text,re.S)
        assert response.status_code == 303 and group
        undo = client.post('/history/undo', data={'group_id':group.group(1)},follow_redirects=False)
        assert undo.status_code == 303
    assert c.reporting.account_balance(bank.id) == 50000
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='OUT'") == 0
