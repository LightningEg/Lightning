"""Faults after payment matching must roll back the entry and its retry marker together."""
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


def test_failed_match_rolls_back_entry_receipt_and_links_then_retry_is_once(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-09-30')
    accounts, cats = setup
    account, category = accounts['cib'], cats['EXP.PERSONAL.FOOD']
    item = c.planning.create(kind='BILL', name='Box', amount='400', frequency='MONTHLY',
                             start_date='2026-09-12', account_id=str(account.id), category_id=str(category.id))
    count = c.db.scalar('SELECT COUNT(*) FROM transactions')
    real_match = c.planning.match_payments
    calls = []
    def fail_after_matching(day):
        calls.append(real_match(day))
        raise ValidationError('Injected settlement failure')
    monkeypatch.setattr(c.planning, 'match_payments', fail_after_matching)
    payload = dict(account_id=str(account.id), kind='out', date='2026-09-13', amount='400',
                   category_id=str(category.id), counterparty='Box', submission='a' * 32)
    client = TestClient(create_app(c))
    failed = client.post('/accounts/quick-add', data=payload)
    assert failed.status_code == 422
    assert calls == [1]  # fail after a real settlement write, not before it
    assert c.db.scalar('SELECT COUNT(*) FROM transactions') == count
    assert c.db.scalar("SELECT COUNT(*) FROM audit_log WHERE entity='form' AND summary=?", ('a' * 32,)) == 0
    assert c.db.scalar('SELECT COUNT(*) FROM planned_payments WHERE planned_item_id=?', (item,)) == 0
    assert c.reporting.account_balance(account.id) == Decimal('50000')
    monkeypatch.setattr(c.planning, 'match_payments', real_match)
    saved = client.post('/accounts/quick-add', data=payload)
    assert saved.status_code == 200 and saved.json()['ok']
    repeated = client.post('/accounts/quick-add', data=payload)
    assert repeated.json()['id'] == saved.json()['id'] and repeated.json()['repeat']
    assert c.db.scalar('SELECT COUNT(*) FROM transactions') == count + 1
    payment = c.planning.payments(c.planning.get(item), '2026-09-30', date(2026, 9, 30))[0]
    assert payment.transaction_id == saved.json()['id']
    assert c.reporting.account_balance(account.id) == Decimal('49600')


def test_atomic_entry_and_payment_link_are_one_undo_action(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-09-30')
    accounts, cats = setup
    account, category = accounts['cib'], cats['EXP.PERSONAL.FOOD']
    item = c.planning.create(kind='BILL', name='Box', amount='400', frequency='MONTHLY',
                             start_date='2026-09-12', account_id=str(account.id), category_id=str(category.id))
    app = create_app(c)
    @app.get('/test-undo-id')
    async def undo_id():
        return c.undo.available()['undo']['id']
    with TestClient(app) as client:
        saved = client.post('/accounts/quick-add', data=dict(account_id=account.id, kind='out', date='2026-09-13',
                            amount='400', category_id=category.id, submission='b' * 32))
        assert saved.status_code == 200
        group_id = client.get('/test-undo-id').json()
        undone = client.post('/history/undo', data={'group_id': group_id}, follow_redirects=False)
        assert undone.status_code == 303
    assert c.reporting.account_balance(account.id) == Decimal('50000')
    assert c.db.scalar('SELECT COUNT(*) FROM planned_payments WHERE planned_item_id=?', (item,)) == 0
