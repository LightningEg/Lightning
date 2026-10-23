"""2M: submitted edit forms cannot overwrite a newer header or posting."""
import re

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


def token(page):
    match = re.search(r'name="revision" value="([a-f0-9]{64})"', page.text)
    assert page.status_code == 200 and match, page.text[:200]
    return match.group(1)


def form(bank, food, *, revision):
    return dict(kind='out', date='2026-09-05', amount='10', category_id=str(food.id),
                category_choice=str(food.id), account_id=str(bank.id), notes='my unsaved note',
                counterparty='', owner_id='', to_account_id='', revision=revision)


@pytest.mark.parametrize('screen', ['popup', 'register', 'global'])
def test_old_form_keeps_newer_amount_and_preserves_unsaved_note(c, setup, screen):
    bank, food = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    txn = c.transactions.record_outflow('2026-09-05', bank.id, '10', food.id)
    get_path = (f'/transactions/{txn.id}/edit-popup' if screen == 'popup' else
                f'/accounts/{bank.id}?edit={txn.id}&acct={bank.id}' if screen == 'register' else
                f'/transactions?edit={txn.id}&acct={bank.id}')
    post_path = (f'/transactions/{txn.id}/edit-popup' if screen == 'popup' else
                 f'/accounts/{bank.id}/register/{txn.id}' if screen == 'register' else
                 f'/transactions/register/{txn.id}')
    with TestClient(create_app(c)) as client:
        revision = token(client.get(get_path))
        c.transactions.update_money(txn.id, txn.date, bank.id, '20', food.id, notes='newer amount')
        values = form(bank, food, revision=revision)
        if screen != 'popup':
            values['amount'] = '-10'
        response = client.post(post_path, data=values)
        assert response.status_code == 400
        assert 'changed since you opened' in response.text
        if screen == 'popup':
            assert response.text.count('class="flash error"') == 1
        assert 'my unsaved note' in response.text
        assert revision in response.text
        # A retry cannot silently acquire a fresh token and overwrite the amount.
        assert client.post(post_path, data=values).status_code == 400
        assert c.transactions.get(txn.id).lines[0].quantity == -20
        assert c.transactions.get(txn.id).notes == 'newer amount'
        values['revision'] = token(client.get(get_path))
        assert client.post(post_path, data=values, follow_redirects=False).status_code == 303
    assert c.transactions.get(txn.id).lines[0].quantity == -10


@pytest.mark.parametrize('change', ['notes', 'category', 'owner', 'void'])
def test_version_covers_header_and_posting_lines_even_when_clock_has_not_advanced(c, setup, change):
    bank, cats = setup[0]['cib'], setup[1]
    txn = c.transactions.record_outflow('2026-09-05', bank.id, '10', cats['EXP.PERSONAL.FOOD'].id)
    old = c.transactions.revision(txn.id)
    if change == 'notes':
        c.transactions.update_metadata(txn.id, txn.date, '', 'another note')
    elif change == 'category':
        c.transactions.set_category([txn.id], cats['EXP.WORK.SOFTWARE'].id)
    elif change == 'owner':
        owner = c.counterparties.ensure_person('Alice')
        c.transactions.record_inflow('2026-09-01', bank.id, '100', cats['EXP.WORK.SALARY'].id, owner_id=owner)
        c.transactions.set_transaction_owner(txn.id, owner)
    else:
        c.transactions.void(txn.id)
    with c.db.transaction(), pytest.raises(ValidationError, match='changed since you opened'):
        c.transactions.require_revision(txn.id, old)


def test_split_save_checks_the_version_before_replacing_any_allocation(c, setup):
    bank, food = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    txn = c.transactions.record_outflow('2026-09-05', bank.id, '10', food.id)
    with TestClient(create_app(c)) as client:
        revision = token(client.get(f'/transactions/{txn.id}'))
        c.transactions.update_money(txn.id, txn.date, bank.id, '20', food.id)
        response = client.post(f'/transactions/{txn.id}/split', data={
            'revision':revision, 'split_category_id':str(food.id), 'split_amount':'10'}, follow_redirects=False)
    assert response.status_code == 303
    assert c.transactions.get(txn.id).lines[0].quantity == -20


def test_revision_refusal_does_not_create_a_counterparty(c, setup):
    bank, food = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    txn = c.transactions.record_outflow('2026-09-05', bank.id, '10', food.id)
    with TestClient(create_app(c)) as client:
        revision = token(client.get(f'/transactions/{txn.id}/edit-popup'))
        c.transactions.update_metadata(txn.id, txn.date, '', 'new')
        values = form(bank, food, revision=revision) | {'counterparty':'Stale new counterparty'}
        assert client.post(f'/transactions/{txn.id}/edit-popup', data=values).status_code == 400
    assert c.counterparties.resolve('Stale new counterparty') is None


from test_journal_finance import devices  # noqa: E402,F401


def test_replica_revision_checked_save_keeps_its_pending_command(devices):
    from lightning.sync.journal.proxy import JournalServices
    hd, pc = devices
    home = JournalServices(hd)
    bank = next(a for a in hd.c.accounts.list() if a.name == 'Bank')
    food = hd.c.categories.get_by_code('EXP.PERSONAL.FOOD')
    txn = home.transactions.record_outflow('2026-09-05', bank.id, '10', food.id)
    pc.sync_with(hd.home)
    record = hd.adapter.uid('transactions', txn.id)
    replica_txn = pc.adapter.local('transactions', record)
    replica_bank = next(a for a in pc.c.accounts.list() if a.name == 'Bank')
    replica_food = pc.c.categories.get_by_code('EXP.PERSONAL.FOOD')
    from test_journal_screens import Screen
    client = Screen(pc)
    revision = token(client.get(f'/transactions/{replica_txn}/edit-popup'))
    response = client.post(f'/transactions/{replica_txn}/edit-popup',
        data=form(replica_bank, replica_food, revision=revision), follow_redirects=False)
    assert response.status_code == 303
    assert len(pc.store.pending()) == 1
    assert pc.c.transactions.get(replica_txn).notes == ''
    pc.sync_with(hd.home)
    assert hd.c.transactions.get(txn.id).notes == 'my unsaved note'
    assert hd.store.fingerprint() == pc.store.fingerprint()


@pytest.mark.parametrize('change', ['account', 'owner'])
def test_stale_popup_cannot_reverse_a_newer_account_or_owner(c, setup, change):
    bank, food = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    txn = c.transactions.record_outflow('2026-09-05', bank.id, '10', food.id)
    with TestClient(create_app(c)) as client:
        revision = token(client.get(f'/transactions/{txn.id}/edit-popup'))
        if change == 'account':
            c.transactions.update_money(txn.id, txn.date, setup[0]['wallet'].id, '10', food.id)
        else:
            owner = c.counterparties.ensure_person('Alice')
            c.transactions.record_inflow('2026-09-01', bank.id, '100', setup[1]['EXP.WORK.SALARY'].id, owner_id=owner)
            c.transactions.set_transaction_owner(txn.id, owner)
        current = c.transactions.get(txn.id)
        response = client.post(f'/transactions/{txn.id}/edit-popup', data=form(bank, food, revision=revision))
    assert response.status_code == 400
    assert c.transactions.get(txn.id) == current
