"""Verified effect-contract upgrades preserve immutable original work."""
import pytest

from test_journal_finance import devices, groups
from test_journal_commands import full_devices
from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.compatibility import UpdateRequired
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import attach
from lightning.sync.journal.snapshots import export
from lightning.sync.journal.store import JournalStore
from lightning.sync.journal.upgrades import upgrade_home, upgrade_replica


def prepare(devices, tmp_path):
    home, peer = devices
    home.save(groups(home, '-10'))
    peer.sync_with(home.home)
    pending = peer.save(groups(peer, '-20'))
    home.save(groups(home, '-30'))
    baseline = home.store.cursor()
    upgrade_home(home.store)
    assert home.store.config['version'] == 3
    assert home.store.cursor() == baseline
    path = tmp_path / 'upgraded-checkpoint.db'
    manifest = export(home.store, path, home.identity.sign)
    return path, manifest, pending


def test_upgrade_preserves_original_pending_bytes_counter_and_confirmed_money(devices, tmp_path):
    home, peer = devices
    path, manifest, pending = prepare(devices, tmp_path)
    with pytest.raises(UpdateRequired):
        peer.sync_with(home.home)
    assert peer.store.pending() == [pending]
    upgrade_replica(peer.store, path, manifest, source_key=home.c.db.copy_key())
    assert peer.store.config['version'] == 3
    assert peer.store.pending() == [pending]
    assert peer.store.db.scalar('SELECT next_seq FROM journal_meta') == 2
    assert peer.store.fingerprint() == home.store.fingerprint()
    current = JournalDevice(peer.store, peer.identity)
    current.sync_with(home.home)
    assert current.store.pending() == []
    assert current.store.fingerprint() == home.store.fingerprint()
    assert {row['name']: row['balance'] for row in current.balances()} == {'Bank': 940, 'Wallet': 100}
    before = home.store.fingerprint()
    assert upgrade_home(home.store) is home.store.adapter
    assert before == home.store.fingerprint()


@pytest.mark.parametrize('phase', ['replica_domain_prepared', 'snapshot_domain', 'snapshot_cursor'])
def test_interrupted_replica_upgrade_keeps_old_format_and_queue_until_atomic_retry(devices, tmp_path, phase):
    home, peer = devices
    path, manifest, pending = prepare(devices, tmp_path)
    before = peer.store.cursor(), peer.store.fingerprint(), dict(peer.store.config)
    def fault(at):
        if at == phase:
            raise RuntimeError('interrupted upgrade')
    with pytest.raises(RuntimeError, match='interrupted upgrade'):
        upgrade_replica(peer.store, path, manifest, source_key=home.c.db.copy_key(), fault=fault)
    assert (peer.store.cursor(), peer.store.fingerprint(), peer.store.config) == before
    assert not peer.store.db.has_table('journal_domain_contract')
    assert peer.store.pending() == [pending]
    with pytest.raises(peer.c.db.driver.DatabaseError):
        peer.c.reserves.create('Bypass', '10')
    upgrade_replica(peer.store, path, manifest, source_key=home.c.db.copy_key())
    assert peer.store.config['version'] == 3
    assert peer.store.pending() == [pending]
    assert peer.store.fingerprint() == home.store.fingerprint()


@pytest.mark.parametrize('phase', ['home_domain_prepared', 'home_domain_committed'])
def test_home_upgrade_resumes_on_reopen_without_reexecuting_old_financial_work(devices, phase):
    home, peer = devices
    home.save(groups(home, '-10'))
    before = home.store.cursor(), home.store.pending()
    def fault(at):
        if at == phase:
            raise RuntimeError('interrupted upgrade')
    with pytest.raises(RuntimeError):
        upgrade_home(home.store, fault=fault)
    expected = 2 if phase == 'home_domain_prepared' else 3
    assert home.store.config['version'] == expected
    reopened = attach(home.c)
    assert reopened.config['version'] == expected
    assert reopened.cursor() == before[0]
    assert reopened.pending() == before[1]
    assert home.c.reporting.account_balance(home.c.accounts.find_by_text('Bank').id) == 990


def test_full_storage_requires_its_domain_contract_before_opening(devices):
    home, peer = devices
    upgrade_home(home.store)
    assert home.store.config['version'] == 3
    home.c.db.conn.set_authorizer(None)
    home.c.db.execute('DROP TABLE journal_domain_contract')
    with pytest.raises(JournalError):
        JournalStore(home.c.db)


def test_new_replica_enrollment_preserves_full_storage_floor(full_devices, tmp_path):
    import asyncio
    from lightning.bootstrap import build
    from lightning.runtime.journal_enrollment import NewJournalReplica
    from lightning.runtime.session import read_slot
    from lightning.security.keys import unwrap_key
    from lightning.sync.journal.codec import unpack
    from test_journal_nearby import setup
    home, peer, identities = full_devices
    source = JournalDevice(home.store, identities[0], home)
    existing = JournalDevice(peer, identities[1])
    pairing = setup([source, existing])
    pairing.begin('Pairing password')
    candidate = unpack(pairing.advertise('0' * 64, 47513))['body'] | dict(endpoint='https://127.0.0.1:47513/pairing/exchange')
    async def search(identity):
        return [candidate]
    def factory(endpoint, certificate, timeout):
        async def request(wire):
            return pairing.enrollment.exchange(wire) if endpoint.endswith('/enrollment/exchange') else pairing.exchange(wire)
        return request
    root = tmp_path / 'new-full-replica'
    client = NewJournalReplica(root, 'New laptop', search=search, client_factory=factory)
    async def enroll():
        found = await client.find()
        digits = await client.join(found[0]['id'], pairing.screen()['code'], 'Pairing password')
        pairing.confirm(digits)
        for _ in range(20):
            if await client.finish('Pairing password', budget=50):
                return
        pytest.fail('Enrollment did not finish within its bounded rounds')
    asyncio.run(enroll())
    key = unwrap_key(read_slot(root / 'keys.json'), 'Pairing password')
    c = build(root / 'ledger.db', key=key, experimental_journal=True)
    try:
        enrolled = attach(c)
        assert enrolled.config['version'] == 3
        assert enrolled.config['role'] == 'replica'
        assert enrolled.adapter.full_domain
        assert enrolled.db.scalar('SELECT next_seq FROM journal_meta') == 1
        assert enrolled.fingerprint() == home.store.fingerprint()
    finally:
        c.db.close()
