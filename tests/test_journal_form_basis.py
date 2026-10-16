"""A rendered form retains its original values and local identity mapping."""
import asyncio

import httpx
import pytest

from test_journal_commands import full_devices
from lightning.runtime.journal_forms import JournalFormGate
from lightning.sync.journal.codec import JournalError, origin_id, unpack
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.form_basis import _file, capture, open_basis, release
from lightning.sync.journal.forms import FormCapture, issue_form, submission_basis
from lightning.sync.journal.store import JournalStore
from lightning.ui.web import create_app


def home_action(home, peer, signer, command, **arguments):
    wire = home.store.adapter.save_action([dict(command=command, arguments=arguments)], signer)
    home.receive(wire)
    home.process()
    assert home.status(origin_id(unpack(wire)['body']['origin']))['status'] == 'accepted', home.status(origin_id(unpack(wire)['body']['origin']))
    for commit in home.store.commits_after(peer.cursor()):
        peer.apply(commit)
    return wire


def test_form_opened_before_an_incoming_budget_change_keeps_original_and_waits_for_review(full_devices):
    home, peer, identities = full_devices
    home_food = home.store.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    food = peer.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    home_action(home, peer, identities[0].sign, 'budgets.set_budget', category_id=home_food, month='2026-09', amount='450')
    path = f'/budget/limit/{food}'
    token = issue_form(peer, path)
    home_action(home, peer, identities[0].sign, 'budgets.set_budget', category_id=home_food, month='2026-09', amount='600')
    current = peer.fingerprint()
    gate = JournalFormGate(create_app(peer.adapter.c), JournalDevice(peer, identities[1]))
    async def save():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gate), base_url='http://testserver') as client:
            response = await client.post(path, data=dict(__journal_form=token, amount='500', month='2026-09'))
            assert response.status_code == 303, response.text
    asyncio.run(save())
    assert peer.fingerprint() == current
    wire, = peer.pending()
    home.receive(wire)
    home.process()
    identifier = origin_id(unpack(wire)['body']['origin'])
    assert home.status(identifier)['status'] == 'review'
    review, = JournalDevice(home.store, identities[0], home).review_items()
    assert ('Amount', '450.00') in review['base_action_shown']
    assert ('Amount', '600.00') in review['current_action_shown']
    assert home.store.adapter.c.budgets.amounts_for('2026-09')[home_food][0] == 600


def test_old_home_form_keeps_its_original_identity_after_archival_and_replacement(full_devices):
    home, peer, identities = full_devices
    c = home.store.adapter.c
    parent = c.categories.get_by_code('EXP.PERSONAL').id
    home_action(home, peer, identities[0].sign, 'categories.create', parent_id=parent, name='Original')
    category = next(row for row in c.categories.pickable() if row.name == 'Original')
    path = f'/categories/{category.id}/edit'
    home_action(home, peer, identities[0].sign, 'budgets.set_budget', category_id=category.id, month='2026-09', amount='10')
    token = issue_form(home.store, path)
    home_action(home, peer, identities[0].sign, 'categories.delete_or_archive', category_id=category.id)
    home_action(home, peer, identities[0].sign, 'categories.create', parent_id=parent, name='Replacement')
    replacement = next(row for row in c.categories.pickable() if row.name == 'Replacement')
    gate = JournalFormGate(create_app(c), JournalDevice(home.store, identities[0], home))
    async def save():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gate), base_url='http://testserver') as client:
            response = await client.post(path, data=dict(__journal_form=token, name='Edited original', active='1'))
            assert response.status_code == 303, response.text
    asyncio.run(save())
    wire, = home.store.pending()
    home.receive(wire)
    home.process()
    assert home.status(origin_id(unpack(wire)['body']['origin']))['status'] == 'review'
    assert c.categories.get(replacement.id).name == 'Replacement'


def test_basis_is_encrypted_nonwritable_and_contains_no_queue_or_transport_credentials(full_devices):
    home, peer, identities = full_devices
    bank = next(account.id for account in peer.adapter.c.accounts.list() if account.name == 'Bank')
    food = peer.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    queued = peer.adapter.save_action([dict(command='transactions.record_outflow', arguments=dict(date='2026-09-01',
        account_id=bank, amount='7', category_id=food, notes='Only in queued payload'))], identities[1].sign)
    with peer.db.transaction():
        peer.db.execute("INSERT INTO journal_local VALUES('transport',?)", ('ab'*32,))
    key = capture(peer)
    assert not _file(peer, key).read_bytes().startswith(b'SQLite format')
    db = open_basis(peer, key)
    try:
        assert db.scalar('SELECT COUNT(*) FROM journal_outbox') == 0
        assert db.scalar('SELECT COUNT(*) FROM journal_inbox') == 0
        assert db.scalar('SELECT COUNT(*) FROM journal_commits') == 0
        assert db.scalar("SELECT COUNT(*) FROM journal_local WHERE name='transport'") == 0
        assert db.scalar('SELECT next_seq FROM journal_meta') == 1
        with pytest.raises(JournalError, match='journal store'):
            JournalStore(db)
    finally:
        db.close()
        release(peer, key)
    assert peer.pending() == [queued]


def test_corrupt_basis_refuses_before_allocation_and_a_new_render_regenerates_it(full_devices):
    home, peer, identities = full_devices
    token = issue_form(peer, '/categories/new')
    key = submission_basis(peer, token, '/categories/new')
    path = _file(peer, key)
    contents = bytearray(path.read_bytes())
    contents[-1] ^= 1
    path.write_bytes(contents)
    with pytest.raises(JournalError, match='original form values'):
        FormCapture(peer, basis_key=key)
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 1
    assert not peer.pending()
    assert capture(peer) == key
    db = open_basis(peer, key)
    db.close()
    release(peer, key)


def test_local_context_changes_and_cache_bounds_do_not_rebase_old_forms(full_devices, monkeypatch):
    from lightning.sync.journal import form_basis
    home, peer, identities = full_devices
    monkeypatch.setattr(form_basis, 'MAX_IMAGES', 2)
    original = peer.fingerprint()
    first = capture(peer)
    with peer.db.transaction(), peer.adapter.writing():
        peer.adapter.c.settings.set('locale', 'ar')
    second = capture(peer)
    assert first != second and peer.fingerprint() == original
    db = open_basis(peer, first)
    try:
        assert db.scalar("SELECT value FROM settings WHERE key='locale'") != 'ar'
    finally:
        db.close()
        release(peer, first)
    for amount in ('100', '200', '300'):
        home_action(home, peer, identities[0].sign, 'profile.set_financial_setting', key='investment_monthly_goal', value=amount)
        capture(peer)
    assert peer.db.scalar('SELECT COUNT(*) FROM journal_form_basis') == 2
    assert len(list(_file(peer, second).parent.glob('*.db'))) == 2
    with pytest.raises(JournalError, match='expired'):
        open_basis(peer, first)


def test_recording_failure_caught_by_a_route_cannot_publish_a_partial_action(full_devices):
    home, peer, identities = full_devices
    before = peer.fingerprint()
    with FormCapture(peer) as form:
        parent = form.container.categories.get_by_code('EXP.PERSONAL').id
        form.container.categories.create(parent, 'Must not publish')
        try:
            form.container.settings.set('budget_bulk_undo', '{}')
        except JournalError:
            pass  # Legacy route handlers may turn a ValueError into a redirect.
        with pytest.raises(JournalError, match='could not be completed'):
            form.finish(identities[1].sign)
    assert peer.fingerprint() == before
    assert not peer.pending()
