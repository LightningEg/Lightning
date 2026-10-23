"""2W: nonfinancial edits must preserve confirmed reserve use and cash figures."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from lightning.undo import user_action


def reserved_expense(c, setup):
    bank = setup[0]['cib'].id
    food = setup[1]['EXP.PERSONAL.FOOD'].id
    txn = c.transactions.record_outflow('2026-09-02', bank, '100', food)
    ids=[]
    for name, used in [('Repairs', '60'), ('Travel', '40')]:
        reserve=c.reserves.create(name, '500')
        c.reserves.allocate(reserve['id'], '500')
        c.reserves.set_expense_link(reserve['id'], txn.id, used)
        ids.append(reserve['id'])
    return txn.id, bank, food, ids


@pytest.mark.parametrize('metadata', [{}, {'notes': 'Receipt attached'}, {'counterparty': 'Shop'}, {'description': 'Groceries'}])
def test_metadata_and_noop_edits_keep_rows_and_both_reserve_links(c, setup, metadata):
    txn, bank, food, reserves = reserved_expense(c, setup)
    rows=c.db.all('SELECT id FROM ledger_entries WHERE transaction_id=?', (txn,))
    before=c.position.at('2026-12-31', match_payments=False).free_cash
    c.transactions.update_money(txn, '2026-09-02', bank, '100', food, **metadata)
    assert [r['id'] for r in c.db.all('SELECT id FROM ledger_entries WHERE transaction_id=?', (txn,))] == [r['id'] for r in rows]
    assert len(c.reserves.links_for_transaction(txn)) == 2
    assert [c.reserves.get(r)['spent'] for r in reserves] == [Decimal('60'), Decimal('40')]
    assert c.position.at('2026-12-31', match_payments=False).free_cash == before


def test_notes_edit_http_and_undo_preserve_confirmed_use(c, setup):
    txn, bank, food, _ = reserved_expense(c, setup)
    reply=TestClient(create_app(c)).post(f'/transactions/{txn}/edit-popup', data={
        'kind':'out', 'date':'2026-09-02', 'amount':'100', 'category_id':food,
        'account_id':bank, 'notes':'Receipt note', 'revision':c.transactions.revision(txn)}, follow_redirects=False)
    assert reply.status_code == 303
    assert len(c.reserves.links_for_transaction(txn)) == 2
    with user_action('Correct note'):
        c.transactions.update_money(txn, '2026-09-02', bank, '100', food, notes='Updated note')
    c.undo.replay()
    assert c.transactions.get(txn).notes == 'Receipt note'
    assert len(c.reserves.links_for_transaction(txn)) == 2
    c.undo.replay(redo=True)
    assert c.transactions.get(txn).notes == 'Updated note'
    assert len(c.reserves.links_for_transaction(txn)) == 2


def test_financial_edit_still_invalidates_reserve_assignment_and_undo_restores_it(c, setup):
    txn, bank, food, _ = reserved_expense(c, setup)
    with user_action('Correct amount'):
        c.transactions.update_money(txn, '2026-09-02', bank, '80', food)
    assert c.reserves.links_for_transaction(txn) == []
    c.undo.replay()
    assert c.transactions.get(txn).lines[0].amount == Decimal('-100')
    assert len(c.reserves.links_for_transaction(txn)) == 2
