"""History replay must preserve postings and refuse impossible dependent holdings."""
from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError
from lightning.undo import user_action


def _position(c, account_id, asset_id):
    holdings, _ = c.reporting.holdings('2026-12-31')
    return next((row.quantity for row in holdings if row.account.id == account_id and row.asset_id == asset_id), Decimal(0))


def test_investment_purchase_undo_and_redo_preserve_cash_units_and_fees(c):
    account = c.account_flows.open_account('Broker', 'BROKERAGE', '2026-09-01', '5000')
    stock = c.assets.create_investment('History stock', 'STOCK', 'HIST')
    with user_action('Buy shares'):
        purchase = c.investments.buy('2026-09-10', account.id, stock.id, '10', '100', fees='5')
    assert c.reporting.account_balance(account.id) == 3995
    assert _position(c, account.id, stock.id) == 10
    c.undo.replay()
    assert c.reporting.account_balance(account.id) == 5000
    assert _position(c, account.id, stock.id) == 0
    c.undo.replay(redo=True)
    assert c.reporting.account_balance(account.id) == 3995
    assert _position(c, account.id, stock.id) == 10
    assert c.transactions.get(purchase.id).is_void is False


def test_undo_cannot_remove_a_purchase_used_by_an_external_sale(c):
    account = c.account_flows.open_account('Broker', 'BROKERAGE', '2026-09-01', '5000')
    stock = c.assets.create_investment('History stock', 'STOCK', 'HIST')
    with user_action('Buy shares'):
        c.investments.buy('2026-09-10', account.id, stock.id, '10', '100')
    # A write outside this window's journal must not leave negative units after undo.
    c.investments.sell('2026-09-20', account.id, stock.id, '5', '110')
    before = c.reporting.account_balance(account.id)
    with pytest.raises(ValidationError):
        c.undo.replay()
    assert c.reporting.account_balance(account.id) == before
    assert _position(c, account.id, stock.id) == 5


def test_editing_a_payment_is_reversible_with_its_original_category_and_amount(c, setup):
    accounts, cats = setup
    bank = accounts['cib'].id
    food = cats['EXP.PERSONAL.FOOD'].id
    software = cats['EXP.WORK.SOFTWARE'].id
    txn = c.transactions.record_outflow('2026-09-10', bank, '42.15', food)
    with user_action('Correct expense'):
        c.transactions.update_money(txn.id, '2026-09-11', bank, '47.25', software, notes='Correction')
    assert c.reporting.account_balance(bank) == Decimal('49952.75')
    c.undo.replay()
    restored = c.transactions.get(txn.id)
    assert restored.date == '2026-09-10' and restored.lines[0].category_id == food
    assert c.reporting.account_balance(bank) == Decimal('49957.85')
    c.undo.replay(redo=True)
    assert c.transactions.get(txn.id).notes == 'Correction'
    assert c.reporting.account_balance(bank) == Decimal('49952.75')


def test_register_payment_and_automatic_bill_link_undo_as_one_http_action(c, setup):
    import re
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, cats = setup
    bank = accounts['cib'].id
    food = cats['EXP.PERSONAL.FOOD'].id
    item = c.planning.create(kind='BILL', name='Groceries box', amount='85', frequency='MONTHLY',
                             start_date='2026-12-30', account_id=str(bank), category_id=str(food))
    def history_id(page, operation):
        body = re.search(r'<form[^>]+action="/history/' + operation + r'"[^>]*>(.*?)</form>', page, re.S)
        assert body, f'{operation} action is visible'
        return re.search(r'name="group_id" value="(\d+)"', body.group(1)).group(1)
    with TestClient(create_app(c)) as client:
        posted = client.post(f'/accounts/{bank}/register', data={
            'date': '2026-12-30', 'amount': '-85', 'category': cats['EXP.PERSONAL.FOOD'].name})
        assert posted.status_code == 200
        group = history_id(posted.text, 'undo')
        assert c.reporting.account_balance(bank) == 49915
        assert c.db.scalar('SELECT count(*) FROM planned_payments WHERE planned_item_id=?', (item,)) == 1
        undone = client.post('/history/undo', data={'group_id': group})
        assert undone.status_code == 200 and 'Action undone.' in undone.text
        assert c.reporting.account_balance(bank) == 50000
        assert c.db.scalar('SELECT count(*) FROM planned_payments WHERE planned_item_id=?', (item,)) == 0
        redo = history_id(undone.text, 'redo')
        redone = client.post('/history/redo', data={'group_id': redo})
        assert redone.status_code == 200 and 'Action redone.' in redone.text
        assert c.reporting.account_balance(bank) == 49915
        assert c.db.scalar('SELECT count(*) FROM planned_payments WHERE planned_item_id=?', (item,)) == 1


def test_every_write_route_is_its_own_undo_action(c, setup):
    """2H: money held for others was missing from the hand-kept list, so Undo reversed the action before it."""
    import re
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, cats = setup
    bank = accounts['cib'].id
    c.counterparties.create('Dad', kind='PERSON')
    def undo_id(page):
        body = re.search(r'<form[^>]+action="/history/undo"[^>]*>(.*?)</form>', page, re.S)
        return re.search(r'name="group_id" value="(\d+)"', body.group(1)).group(1) if body else None
    with TestClient(create_app(c)) as client:
        expense = client.post(f'/accounts/{bank}/register', data={
            'date': '2026-09-10', 'amount': '-40', 'category': cats['EXP.PERSONAL.FOOD'].name})
        before = undo_id(expense.text)
        assert before and c.reporting.account_balance(bank) == 49960
        held = c.reporting.money_from_others_history()
        saved = client.post('/money-from-others', data={'owner': 'Dad', 'account_id': str(bank), 'amount': '500',
                                                        'date': '2026-09-12'})
        assert saved.status_code == 200 and c.reporting.money_from_others_history() != held
        latest = undo_id(saved.text)
        assert latest and latest != before
        undone = client.post('/history/undo', data={'group_id': latest})
        assert undone.status_code == 200 and 'Action undone.' in undone.text
    assert c.reporting.money_from_others_history() == held
    assert c.reporting.account_balance(bank) == 49960  # the earlier expense stays
