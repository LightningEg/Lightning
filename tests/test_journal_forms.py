"""Existing service calls are captured without changing confirmed balances."""
import pytest

from test_journal_commands import full_devices
from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.forms import FormCapture


def accept(home, peer, wire):
    home.receive(wire)
    home.process()
    for commit in home.store.commits_after(peer.cursor()):
        peer.apply(commit)
    assert not peer.pending()
    assert home.store.fingerprint() == peer.fingerprint()


def test_existing_transaction_service_form_saves_pending_then_replays_exactly(full_devices):
    home, peer, identities = full_devices
    c = peer.adapter.c
    before = peer.fingerprint()
    bank = next(account for account in c.accounts.list() if account.name == 'Bank')
    category = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    with FormCapture(peer) as form:
        transaction = form.container.transactions.record_outflow('2026-09-01', bank.id, '7.35', category.id)
        assert transaction.id
        assert peer.fingerprint() == before
        wire = form.finish(identities[1].sign)
    assert peer.fingerprint() == before
    assert len(peer.pending()) == 1
    accept(home, peer, wire)


def test_multi_call_form_and_financial_preferences_are_one_atomic_action(full_devices):
    home, peer, identities = full_devices
    before = peer.fingerprint()
    with FormCapture(peer) as form:
        form.container.categories.create(form.container.categories.get_by_code('EXP.PERSONAL').id, 'Food away')
        form.container.settings.set('investment_monthly_goal', '700')
        wire = form.finish(identities[1].sign)
    assert peer.fingerprint() == before
    accept(home, peer, wire)
    assert peer.adapter.c.settings.get('investment_monthly_goal') == '700'


def test_unrecorded_financial_write_refuses_before_allocating_an_origin(full_devices):
    home, peer, identities = full_devices
    before = peer.fingerprint()
    with FormCapture(peer) as form:
        form.container.categories.create(form.container.categories.get_by_code('EXP.PERSONAL').id, 'Recorded')
        form.shadow.settings.set('investment_monthly_goal', '900')
        with pytest.raises(JournalError, match='outside its journal commands'):
            form.finish(identities[1].sign)
    assert peer.fingerprint() == before
    assert not peer.pending()
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 1


def test_cancelled_form_and_noop_do_not_allocate_and_local_preferences_require_own_lane(full_devices):
    home, peer, identities = full_devices
    before = peer.fingerprint()
    with FormCapture(peer) as form:
        form.container.categories.create(form.container.categories.get_by_code('EXP.PERSONAL').id, 'Cancelled')
    assert peer.fingerprint() == before
    assert not peer.pending()
    with FormCapture(peer) as form:
        assert form.finish(identities[1].sign) is None
        with pytest.raises(JournalError, match='already ended'):
            form.finish(identities[1].sign)
    with FormCapture(peer) as form:
        with pytest.raises(JournalError, match='local settings lane'):
            form.container.settings.set('locale', 'ar')
    assert not peer.pending()


def test_form_retry_returns_original_slot_and_changed_payload_is_refused(full_devices):
    from lightning.sync.journal.forms import issue_form, prior_submission
    from lightning.sync.journal.codec import digest
    home, peer, identities = full_devices
    token = issue_form(peer, '/categories/new')
    submission = (token, '/categories/new', digest(dict(name='New')))
    with FormCapture(peer) as form:
        form.container.categories.create(form.container.categories.get_by_code('EXP.PERSONAL').id, 'New')
        wire = form.finish(identities[1].sign, submission=submission)
    assert prior_submission(peer, *submission) == wire
    with FormCapture(peer) as form:
        assert form.finish(identities[1].sign, submission=submission) == wire
    with pytest.raises(JournalError, match='different values'):
        prior_submission(peer, token, '/categories/new', digest(dict(name='Changed')))
    with pytest.raises(JournalError, match='expired'):
        prior_submission(peer, token, '/categories/other', submission[2])
    assert len(peer.pending()) == 1
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 2
    accept(home, peer, wire)


def test_actual_register_form_saves_once_without_changing_confirmed_money(full_devices):
    import asyncio
    import re
    import httpx
    from lightning.runtime.journal_forms import JournalFormGate
    from lightning.sync.journal.device import JournalDevice
    from lightning.ui.web import create_app
    home, peer, identities = full_devices
    device = JournalDevice(peer, identities[1])
    app = create_app(peer.adapter.c)
    gate = JournalFormGate(app, device)
    bank = next(account for account in peer.adapter.c.accounts.list() if account.name == 'Bank')
    before = peer.fingerprint()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gate), base_url='http://testserver') as client:
            page = await client.get(f'/accounts/{bank.id}')
            assert page.status_code == 200
            found = re.search(r'<form[^>]*action="/accounts/'+str(bank.id)+r'/register"[^>]*>(.*?)</form>', page.text, re.S)
            assert found is not None
            token = re.search(r'name="__journal_form" value="([^"]+)"', found[1])[1]
            data = dict(__journal_form=token, date='01/09/2026', amount='-7.35', category='Food',
                        category_choice=str(peer.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD').id),
                        counterparty='', counterparty_choice='', counterparty_typed='', whom='', notes='Coffee')
            first = await client.post(f'/accounts/{bank.id}/register', data=data)
            assert first.status_code == 303, first.text
            assert 'Waiting+for+confirmation' in first.headers['location']
            assert peer.fingerprint() == before
            second = await client.post(f'/accounts/{bank.id}/register', data=data)
            assert second.status_code == 303
            assert len(peer.pending()) == 1
            assert app.state.container is peer.adapter.c
            changed = await client.post(f'/accounts/{bank.id}/register', data=data | dict(amount='-9'))
            assert changed.status_code == 409
            refused = await client.post('/settings/import', data=data)
            assert refused.status_code == 409
            assert len(peer.pending()) == 1
    asyncio.run(run())
    accept(home, peer, peer.pending()[0])


def test_confirmed_change_during_an_await_cannot_rebase_a_stale_form(full_devices):
    home, peer, identities = full_devices
    with FormCapture(peer) as form:
        form.container.categories.create(form.container.categories.get_by_code('EXP.PERSONAL').id, 'Stale')
        # Simulate foreground synchronization between two route awaits.
        wire = home.store.adapter.save_action([dict(command='profile.set_financial_setting',
            arguments=dict(key='investment_monthly_goal', value='600'))], identities[0].sign)
        home.receive(wire)
        home.process()
        for commit in home.store.commits_after(peer.cursor()):
            peer.apply(commit)
        with pytest.raises(JournalError, match='confirmed ledger changed'):
            form.finish(identities[1].sign)
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 1
    assert not peer.pending()


def test_form_retry_cannot_acknowledge_before_failed_private_checkpoint_recovers(full_devices, tmp_path, monkeypatch):
    import json
    from test_journal_authority import memories
    from lightning.sync.journal.device import JournalDevice
    from lightning.sync.journal.forms import issue_form, prior_submission
    from lightning.sync.journal.codec import digest
    from lightning.sync.journal.watermark import Watermark
    home, peer, identities = full_devices
    _, controls = memories([JournalDevice(home.store, identities[0], home), JournalDevice(peer, identities[1])], tmp_path)
    try:
        token = issue_form(peer, '/categories/new')
        submission = (token, '/categories/new', digest(dict(name='New')))
        write = Watermark._write
        def fail(*args):
            raise OSError('private disk full')
        with FormCapture(peer) as form:
            form.container.categories.create(form.container.categories.get_by_code('EXP.PERSONAL').id, 'New')
            monkeypatch.setattr(Watermark, '_write', fail)
            with pytest.raises(OSError, match='private disk full'):
                form.finish(identities[1].sign, submission=submission)
        wire, = peer.pending()
        assert json.loads(controls[1].db.execute('SELECT document FROM origin_checkpoint').fetchone()[0])['seq'] == 0
        with pytest.raises(OSError, match='private disk full'):
            prior_submission(peer, *submission)
        monkeypatch.setattr(Watermark, '_write', write)
        assert prior_submission(peer, *submission) == wire
        assert json.loads(controls[1].db.execute('SELECT document FROM origin_checkpoint').fetchone()[0])['seq'] == 1
        assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 2
    finally:
        for control in controls:
            control.close()


def test_form_retry_after_compaction_returns_proof_without_recreating_financial_payload(full_devices):
    from datetime import datetime, timedelta, timezone
    from lightning.sync.journal.forms import issue_form, prior_submission
    from lightning.sync.journal.codec import digest, origin_id, unpack
    from lightning.sync.journal.retention import Retention
    home, peer, identities = full_devices
    token = issue_form(peer, '/categories/new')
    submission = (token, '/categories/new', digest(dict(name='Private category')))
    with FormCapture(peer) as form:
        form.container.categories.create(form.container.categories.get_by_code('EXP.PERSONAL').id, 'Private category')
        wire = form.finish(identities[1].sign, submission=submission)
    accept(home, peer, wire)
    identifier = origin_id(unpack(wire)['body']['origin'])
    peer.mark_displayed(identifier)
    retention = Retention(home.store, signer=identities[0].sign, clock=lambda: datetime.now(timezone.utc)+timedelta(days=31))
    retention.acknowledge(peer.config['device'], peer.config['incarnation'], peer.cursor())
    assert retention.compact() == 1
    compact = home.decision(identifier)
    local = Retention(peer, clock=lambda: datetime.now(timezone.utc)+timedelta(days=31))
    local.accept_receipt(compact)
    local.prune_local()
    proof = prior_submission(peer, *submission)
    assert unpack(proof)['body']['type'] == 'compact-receipt'
    assert b'Private category' not in proof
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 2
    assert not peer.pending()
