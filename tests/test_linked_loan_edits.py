"""2V: ledger corrections cannot silently invalidate confirmed loan repayments."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app
from lightning.undo import user_action


def loan_payment(c, setup, amount='100'):
    accounts, cats = setup
    bank, food = accounts['cib'].id, cats['EXP.PERSONAL.FOOD'].id
    item = c.planning.create(kind='LOAN', name='Car', amount='100', payment_count='3', principal='300',
                             start_date='2026-09-02', account_id=bank, category_id=food)
    txn = c.planning.record_payment(item, '2026-09-02', '2026-09-02', amount, bank)
    return item, txn, bank, food


@pytest.mark.parametrize('change', ['amount_down', 'amount_up', 'date', 'account', 'category', 'owner', 'split_owner'])
def test_linked_repayment_changes_are_refused_atomically(c, setup, change):
    item, txn, bank, food = loan_payment(c, setup)
    before = c.transactions.get(txn)
    owner = c.counterparties.create('Saved person')
    with pytest.raises(ValidationError, match='Reopen this loan payment'):
        if change == 'owner':
            c.transactions.set_transaction_owner(txn, owner)
        elif change == 'split_owner':
            c.transactions.mark_line_owner(txn, bank, before.lines[0].asset_id, -10000000, owner)
        else:
            c.transactions.update_money(txn, '2026-09-03' if change == 'date' else before.date,
                setup[0]['wallet'].id if change == 'account' else bank,
                '10' if change == 'amount_down' else '120' if change == 'amount_up' else '100',
                setup[1]['EXP.WORK.SOFTWARE'].id if change == 'category' else food)
    assert c.transactions.get(txn) == before
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay'] == Decimal('200')


def test_normal_http_edit_explains_reopen_and_keeps_loan_and_cash(c, setup):
    item, txn, bank, food = loan_payment(c, setup)
    response = TestClient(create_app(c)).post(f'/transactions/{txn}/edit-popup', data={
        'kind': 'out', 'date': '2026-09-02', 'amount': '10', 'category_id': food,
        'account_id': bank, 'revision': c.transactions.revision(txn)}, follow_redirects=False)
    assert response.status_code == 400 and 'Reopen this loan payment' in response.text
    assert c.reporting.account_balance(bank) == Decimal('49900')
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay'] == Decimal('200')


def test_explicit_reopen_and_correction_undo_together(c, setup):
    item, txn, bank, food = loan_payment(c, setup)
    with user_action('Correct linked loan payment'):
        c.planning.reopen(item, '2026-09-02')
        c.transactions.update_money(txn, '2026-09-02', bank, '60', food)
        c.planning.mark_paid(item, '2026-09-02', txn)
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay'] == Decimal('240')
    c.undo.replay()
    assert c.transactions.get(txn).lines[0].amount == Decimal('-100')
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay'] == Decimal('200')


def test_partial_and_extra_loan_payments_require_explicit_correction(c, setup):
    item, txn, bank, food = loan_payment(c, setup, '10')
    c.transactions.update_money(txn, '2026-09-02', bank, '10', food, notes='Receipt note')
    assert c.transactions.get(txn).notes == 'Receipt note'
    extra = c.planning.record_payment(item, '2026-09-02', '2026-09-03', '20', bank)
    with pytest.raises(ValidationError, match='Void this loan repayment'):
        c.transactions.update_money(extra, '2026-09-03', bank, '15', food)
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay'] == Decimal('270')
    c.transactions.void(extra)
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay'] == Decimal('290')


def test_undo_of_an_older_edit_cannot_drift_a_later_confirmation(c, setup):
    bank, food = setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    txn = c.transactions.record_outflow('2026-09-02', bank, '50', food)
    with user_action('Correct expense'):
        c.transactions.update_money(txn.id, '2026-09-02', bank, '100', food)
    item = c.planning.create(kind='LOAN', name='Car', amount='100', payment_count='3',
                             start_date='2026-09-02', account_id=bank, category_id=food)
    c.planning.mark_paid(item, '2026-09-02', txn.id)
    with pytest.raises(ValidationError, match='Reopen this loan payment'):
        c.undo.replay()
    assert c.transactions.get(txn.id).lines[0].amount == Decimal('-100')
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay'] == Decimal('200')
