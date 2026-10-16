"""History expires; original identities, decisions and causal tokens do not."""
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest

from lightning.sync.identity import load_or_create
from lightning.sync.journal.codec import JournalError, ZERO_HASH, origin_id, unpack
from lightning.sync.journal.home import JournalHome
from lightning.sync.journal.retention import Retention, SnapshotRequired, validate_receipt
from lightning.sync.journal.store import JournalStore
from test_journal_commands import full_devices, submit


@pytest.fixture
def history(tmp_path):
    identities = [load_or_create(tmp_path / f'identity-{i}', f'Device {i}') for i in range(2)]
    profile, generation = str(uuid4()), str(uuid4())
    stores = [JournalStore.create(tmp_path / f'device-{i}.db', key=os.urandom(32), profile=profile,
               generation=generation, device=identity.device_id, incarnation=str(uuid4()), home_key=identities[0].public_key,
               origin_key=identity.public_key, role='replica' if i else 'home') for i, identity in enumerate(identities)]
    home = JournalHome(stores[0], identities[0].sign)
    for store, identity in zip(stores, identities):
        home.approve_origin(identity.device_id, store.config['incarnation'], identity.public_key)
    clock = datetime.now(timezone.utc)
    retention = [Retention(stores[0], signer=identities[0].sign, clock=lambda: clock + timedelta(days=31)),
                 Retention(stores[1], clock=lambda: clock + timedelta(days=31))]
    yield home, stores[1], identities, retention
    for store in stores:
        store.close()


def save(history, *, kind='dummy.add', record=None, groups=None, bases=None, dependencies=()):
    home, peer, identities, _ = history
    wire = peer.save(kind=kind, record=record or str(uuid4()), groups=groups or {'details': {'note': 'Private narrative'}},
                     bases=bases or {'details': None}, dependencies=dependencies, signer=identities[1].sign)
    home.receive(wire)
    commit, = home.process()
    peer.apply(commit)
    return wire, commit


def ack(history):
    home, peer, _, retention = history
    retention[0].acknowledge(peer.config['device'], peer.config['incarnation'], peer.cursor())


def test_compaction_waits_for_every_approved_device_and_keeps_retry_receipt(history):
    home, peer, _, retention = history
    original, commit = save(history)
    cursor = home.store.cursor()
    assert retention[0].compact() == 0
    ack(history)
    assert retention[0].compact() == 1
    compact = home.decision(origin_id(unpack(original)['body']['origin']))
    body = unpack(compact)['body']
    validate_receipt(body)
    assert b'Private narrative' not in compact
    assert body['commit_hash'] == cursor['hash']
    assert home.receive(original) == 'accepted'
    assert home.process() == []
    assert home.store.cursor() == cursor
    with pytest.raises(SnapshotRequired):
        home.store.commits_after(dict(revision=0, hash=ZERO_HASH))
    assert home.store.commits_after(cursor) == []


def test_absent_device_blocks_pruning_until_deliberate_revocation(history):
    home, peer, _, retention = history
    save(history)
    assert retention[0].compact() == 0
    home.revoke_origin(peer.config['device'], peer.config['incarnation'])
    assert retention[0].compact() == 1
    with pytest.raises(JournalError, match='approved'):
        ack(history)


def test_thirty_day_minimum_is_independent_of_device_acknowledgements(history):
    home, peer, _, _ = history
    save(history)
    ack(history)
    early = Retention(home.store, signer=history[2][0].sign, clock=lambda: datetime.now(timezone.utc) + timedelta(days=29))
    assert early.compact() == 0
    assert unpack(home.decision(peer.db.scalar('SELECT proposal_id FROM journal_outbox')))['body']['type'] == 'commit'


def test_rejected_payload_is_retained_until_a_week_after_first_display(history):
    home, peer, _, retention = history
    original, commit = save(history, kind='dummy.edit')  # missing record
    identifier = origin_id(unpack(original)['body']['origin'])
    assert unpack(commit)['body']['outcome'] == 'rejected'
    assert retention[1].prune_local() == 0  # Even at 31 days: never displayed.
    peer.mark_displayed(identifier)
    recent = Retention(peer, clock=lambda: datetime.now(timezone.utc) + timedelta(days=6))
    assert recent.prune_local() == 0
    assert retention[1].prune_local() == 1
    saved = bytes(peer.db.scalar('SELECT wire FROM journal_outbox'))
    assert b'Private narrative' not in saved
    assert unpack(saved)['body']['proposal_hash'] == unpack(commit)['body']['proposal_hash']
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 2
    assert peer.db.scalar('SELECT COUNT(*) FROM journal_outbox') == 1
    assert retention[1].prune_local() == 0
    reopened = JournalStore(peer.db)
    assert reopened.pending() == []


def test_undecided_proposal_is_retained_regardless_of_age(history):
    _, peer, identities, retention = history
    original = peer.save(kind='dummy.add', record=str(uuid4()), groups={'details': 'Never uploaded'},
                         bases={'details': None}, signer=identities[1].sign)
    assert retention[1].prune_local() == 0
    assert peer.pending() == [original]


def test_accepted_payload_waits_for_display_and_verified_compact_proof(history):
    home, peer, _, retention = history
    original, _ = save(history)
    identifier = origin_id(unpack(original)['body']['origin'])
    peer.mark_displayed(identifier)
    assert retention[1].prune_local() == 0
    ack(history)
    retention[0].compact()
    proof = home.decision(identifier)
    assert retention[1].accept_receipt(proof)
    assert retention[1].prune_local() == 1
    assert bytes(peer.db.scalar('SELECT wire FROM journal_outbox')) == proof
    assert peer.cursor() == home.store.cursor()
    assert peer.fingerprint() == home.store.fingerprint()
    assert JournalStore(peer.db).pending() == []


def test_compact_receipts_keep_dependency_tokens(history):
    home, peer, _, retention = history
    original, _ = save(history)
    proposal = unpack(original)['body']
    ack(history)
    retention[0].compact()
    changed, commit = save(history, kind='dummy.edit', record=proposal['record'],
                           groups={'details': {'note': 'New value'}}, dependencies=[proposal['origin']])
    assert unpack(commit)['body']['outcome'] == 'accepted'
    assert peer.record(proposal['record'])['groups']['details']['note'] == 'New value'
    assert peer.fingerprint() == home.store.fingerprint()


def test_acknowledgements_are_monotonic_and_never_accept_unknown_checkpoints(history):
    home, peer, _, retention = history
    save(history)
    ack(history)
    assert not retention[0].acknowledge(peer.config['device'], peer.config['incarnation'], dict(revision=0, hash=ZERO_HASH))
    with pytest.raises(JournalError, match='Unknown checkpoint'):
        retention[0].acknowledge(peer.config['device'], peer.config['incarnation'], dict(revision=99, hash='a' * 64))
    with pytest.raises(JournalError, match='approved'):
        retention[0].acknowledge(peer.config['device'], str(uuid4()), peer.cursor())


def test_old_and_pruned_backups_preserve_receipts_and_never_rehydrate_expired_payload(full_devices, tmp_path):
    from lightning.sync.journal.backups import create, recover_queue
    from lightning.sync.journal.device import JournalDevice
    from lightning.security.keys import key_id
    home, peer, identities = full_devices
    device = JournalDevice(peer, identities[1])
    wire = submit(full_devices, 'reserves.create', name='Private trip', target='10.01')
    identifier = origin_id(unpack(wire)['body']['origin'])
    keys = dict(key_id=key_id(peer.db.copy_key()), opaque='dummy-only')
    old_path = tmp_path / 'old-backup.db'
    old_manifest = create(device, old_path, key_document=keys)
    peer.mark_displayed(identifier)
    future = lambda: datetime.now(timezone.utc) + timedelta(days=31)
    keeper = Retention(home.store, signer=identities[0].sign, clock=future)
    keeper.acknowledge(peer.config['device'], peer.config['incarnation'], peer.cursor())
    keeper.compact()
    local = Retention(peer, clock=future)
    local.accept_receipt(home.decision(identifier))
    assert local.prune_local() == 1
    proof = bytes(peer.db.scalar('SELECT wire FROM journal_outbox'))
    assert b'Private trip' not in proof
    assert recover_queue(device, old_path, old_manifest, backup_key=peer.db.copy_key()) == 0
    assert bytes(peer.db.scalar('SELECT wire FROM journal_outbox')) == proof
    new_path = tmp_path / 'pruned-backup.db'
    new_manifest = create(device, new_path, key_document=keys)
    peer.db.execute('DELETE FROM journal_outbox')  # fault: lost slot, retained high water
    assert recover_queue(device, new_path, new_manifest, backup_key=peer.db.copy_key()) == 1
    assert bytes(peer.db.scalar('SELECT wire FROM journal_outbox')) == proof
    assert JournalStore(peer.db).pending() == []
    assert peer.fingerprint() == home.store.fingerprint()


def test_returned_device_uses_full_checkpoint_after_compaction(full_devices, tmp_path):
    from lightning.sync.journal.snapshots import export, repair
    home, peer, identities = full_devices
    submit(full_devices, 'reserves.create', name='Trip', target='10.01')
    future = lambda: datetime.now(timezone.utc) + timedelta(days=31)
    keeper = Retention(home.store, signer=identities[0].sign, clock=future)
    keeper.acknowledge(peer.config['device'], peer.config['incarnation'], peer.cursor())
    keeper.compact()
    source = tmp_path / 'compacted-checkpoint.db'
    manifest = export(home.store, source, identities[0].sign)
    repair(peer, source, manifest, source_key=home.db.copy_key())
    assert peer.fingerprint() == home.store.fingerprint()
    assert unpack(bytes(peer.db.scalar('SELECT wire FROM journal_commits')))['body']['type'] == 'compact-receipt'
    assert peer.pending() == []
    submit(full_devices, 'reserves.create', name='After return', target='12.34')


def test_authenticated_lan_round_durably_acknowledges_the_correct_incarnation(full_devices):
    import asyncio
    from lightning.sync.journal.device import JournalDevice
    from lightning.sync.journal.local import LocalChannel
    home, peer, identities = full_devices
    submit(full_devices, 'reserves.create', name='Trip', target='10')
    secret = os.urandom(32)
    server = LocalChannel(JournalDevice(home.store, identities[0], home), transport_key=secret,
                          peers={identities[1].device_id: identities[1].public_key})
    client = LocalChannel(JournalDevice(peer, identities[1]), transport_key=secret,
                          peers={identities[0].device_id: identities[0].public_key})
    async def request(wire):
        return server.handle(wire)
    asyncio.run(client.synchronize(request, home_id=identities[0].device_id))
    ack = home.db.one('SELECT * FROM journal_acks WHERE device=? AND incarnation=?', (peer.config['device'], peer.config['incarnation']))
    assert ack['revision'] == peer.cursor()['revision']
    assert ack['hash'] == peer.cursor()['hash']
    forged = client.protect(dict(operation='ack', value=dict(incarnation=str(uuid4()), cursor=peer.cursor())), identities[0].device_id)
    with pytest.raises(JournalError, match='incarnation'):
        server.handle(forged)


def test_expired_payload_is_also_removed_from_duplicate_mailbox_caches(full_devices):
    from lightning.sync.journal.device import JournalDevice
    from lightning.sync.journal.local import LocalChannel, encode
    from lightning.sync.journal.cloud import MailboxPeer, MailboxExchange
    home, peer, identities = full_devices
    original = submit(full_devices, 'reserves.create', name='Private trip', target='10')
    channel = LocalChannel(JournalDevice(peer, identities[1]), transport_key=os.urandom(32),
                           peers={identities[0].device_id: identities[0].public_key})
    mailbox = MailboxPeer(channel, None)
    rpc = MailboxExchange(mailbox)
    envelope = rpc.prepare(dict(operation='proposal', value=encode(original)), identities[0].device_id)
    mailbox.enqueue(envelope)
    peer.db.execute("INSERT INTO journal_mail_in VALUES('processed','sender',?,1)", (envelope,))
    peer.db.execute("INSERT INTO journal_mail_in VALUES('undecided','sender',?,0)", (envelope,))
    future = lambda: datetime.now(timezone.utc) + timedelta(days=31)
    keeper = Retention(home.store, signer=identities[0].sign, clock=future)
    keeper.acknowledge(peer.config['device'], peer.config['incarnation'], peer.cursor())
    keeper.compact()
    identifier = origin_id(unpack(original)['body']['origin'])
    peer.mark_displayed(identifier)
    local = Retention(peer, clock=future)
    local.accept_receipt(home.decision(identifier))
    assert local.prune_local() == 1
    assert not peer.db.scalar('SELECT COUNT(*) FROM journal_rpc')
    assert not peer.db.scalar('SELECT COUNT(*) FROM journal_mail_out')
    assert not peer.db.scalar("SELECT COUNT(*) FROM journal_local WHERE name LIKE 'rpc_proposal:%'")
    assert [row['id'] for row in peer.db.all('SELECT id FROM journal_mail_in')] == ['undecided']


def test_even_home_signed_compaction_cannot_change_known_dependency_tokens(history):
    from lightning.sync.journal.codec import seal
    home, peer, identities, retention = history
    original, _ = save(history)
    ack(history)
    retention[0].compact()
    proof = home.decision(origin_id(unpack(original)['body']['origin']))
    body = unpack(proof)['body']
    body['effects'][0]['tokens']['details'] = '0' * 64
    cursor, fingerprint = peer.cursor(), peer.fingerprint()
    with pytest.raises(JournalError, match='dependency tokens'):
        retention[1].accept_receipt(seal(body, identities[0].sign))
    assert peer.cursor() == cursor and peer.fingerprint() == fingerprint


def test_inherited_receipt_is_reattested_and_backup_uses_current_verified_decision(full_devices, tmp_path):
    from lightning.security.keys import key_id
    from lightning.sync.journal.backups import create, recover_queue
    from lightning.sync.journal.codec import authenticate, canonical
    from lightning.sync.journal.device import JournalDevice
    from lightning.sync.journal.local import LocalChannel, decode
    home, peer, identities = full_devices
    original = submit(full_devices, 'reserves.create', name='Trip', target='10')
    identifier = origin_id(unpack(original)['body']['origin'])
    future = lambda: datetime.now(timezone.utc) + timedelta(days=31)
    keeper = Retention(home.store, signer=identities[0].sign, clock=future)
    keeper.acknowledge(peer.config['device'], peer.config['incarnation'], peer.cursor())
    keeper.compact()
    old_proof = home.decision(identifier)
    local = Retention(peer, clock=future)
    local.accept_receipt(old_proof)
    peer.mark_displayed(identifier)
    local.prune_local()
    # Inject the new pinned key, independently of the separately tested owner
    # transition state machine. The inherited stream and old receipt stay exact.
    successor = load_or_create(tmp_path / 'successor', 'Successor')
    for store in (home.store, peer):
        store.config['home_key'] = successor.public_key
        store.db.execute('UPDATE journal_meta SET config=?', (canonical(store.config).decode(),))
    home.signer = successor.sign
    secret = os.urandom(32)
    server = LocalChannel(JournalDevice(home.store, identities[0], home), transport_key=secret,
                          peers={identities[1].device_id: identities[1].public_key})
    client = LocalChannel(JournalDevice(peer, identities[1]), transport_key=secret,
                          peers={identities[0].device_id: identities[0].public_key})
    request = client.protect(dict(operation='receipts', value=[1]), identities[0].device_id)
    _, response = client.open(server.handle(request))
    proof = decode(response['result']['1'])
    authenticate(unpack(proof), successor.public_key)
    assert unpack(proof)['body'] == unpack(old_proof)['body']
    assert local.accept_receipt(proof)
    path = tmp_path / 'inherited-backup.db'
    device = JournalDevice(peer, identities[1])
    manifest = create(device, path, key_document=dict(key_id=key_id(peer.db.copy_key()), opaque='dummy'))
    peer.db.execute('DELETE FROM journal_outbox')
    assert recover_queue(device, path, manifest, backup_key=peer.db.copy_key()) == 1
    assert peer.pending() == []
    assert peer.fingerprint() == home.store.fingerprint()
