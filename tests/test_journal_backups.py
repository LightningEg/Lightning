"""Encrypted local queue recovery never rewinds money, identity or origin counter."""
import json
import os
from uuid import uuid4

import pytest

from test_journal_finance import devices, groups
from lightning.sync.journal.backups import create, recover_queue, restore_copy, repropose_copy
from lightning.sync.journal.codec import JournalError, seal, unpack, origin_id


def backup(pc, path):
    from lightning.security.keys import key_id
    # The wrapper is opaque to the package; separate key tests verify real locks.
    keys = dict(key_id=key_id(pc.c.db.copy_key()), opaque="dummy-wrapped-key-material")
    return create(pc, path, key_document=keys)


def test_older_backup_keeps_newer_queue_counter_and_confirmed_money(devices, tmp_path):
    home, pc = devices
    pc.save(groups(pc))
    source = tmp_path / "backup.db"
    manifest = backup(pc, source)
    pc.save(groups(pc, "-18"))
    pc.sync_with(home.home)
    before = pc.store.fingerprint()
    assert recover_queue(pc, source, manifest, backup_key=pc.c.db.copy_key()) == 0
    assert pc.store.fingerprint() == before
    assert pc.c.db.scalar("SELECT next_seq FROM journal_meta") == 3
    wire = pc.save(groups(pc, "-11"))
    assert unpack(wire)["body"]["origin"]["seq"] == 3
    data = source.read_bytes()
    assert not data.startswith(b"SQLite format")
    assert b"PRIVATE KEY" not in data and b"dummy-wrapped-key-material" not in data


@pytest.mark.parametrize("phase", ["queue_imported", "queue_counter"])
def test_pending_recovery_and_counter_change_are_atomic(devices, tmp_path, phase):
    _, pc = devices
    original = pc.save(groups(pc))
    source = tmp_path / "backup.db"
    manifest = backup(pc, source)
    # Simulate local loss after backup, retaining the uncertain high-water counter.
    pc.c.db.execute("DELETE FROM journal_outbox")
    class Exit(Exception):
        pass
    def crash(at):
        if at == phase:
            raise Exit
    before = pc.store.fingerprint()
    with pytest.raises(Exit):
        recover_queue(pc, source, manifest, backup_key=pc.c.db.copy_key(), fault=crash)
    assert pc.c.db.scalar("SELECT COUNT(*) FROM journal_outbox") == 0
    assert pc.c.db.scalar("SELECT next_seq FROM journal_meta") == 2
    assert recover_queue(pc, source, manifest, backup_key=pc.c.db.copy_key()) == 1
    assert pc.store.pending() == [original]
    assert pc.store.fingerprint() == before
    assert pc.c.db.scalar("SELECT next_seq FROM journal_meta") == 2


def test_changed_backup_bytes_or_another_device_cannot_restore_an_origin(devices, tmp_path):
    home, pc = devices
    pc.save(groups(pc))
    source = tmp_path / "backup.db"
    manifest = backup(pc, source)
    with pytest.raises(JournalError):
        recover_queue(home, source, manifest, backup_key=pc.c.db.copy_key())
    with source.open("r+b") as handle:
        handle.seek(100)
        handle.write(b"bad")
    with pytest.raises(JournalError, match="hash"):
        recover_queue(pc, source, manifest, backup_key=pc.c.db.copy_key())


def test_signed_manifest_must_describe_the_saved_checkpoint(devices, tmp_path):
    _, pc = devices
    pc.save(groups(pc))
    source = tmp_path / "backup.db"
    manifest = backup(pc, source)
    body = unpack(manifest)["body"] | {"fingerprint": "0" * 64}
    forged = seal(body, pc.identity.sign)
    with pytest.raises(JournalError, match="manifest"):
        recover_queue(pc, source, forged, backup_key=pc.c.db.copy_key())


def test_restore_copy_is_quarantined_and_preserves_original_identity(devices, tmp_path):
    _, pc = devices
    pc.save(groups(pc))
    source = tmp_path / "backup.db"
    manifest = backup(pc, source)
    target = tmp_path / "restored" / "comparison.db"
    descriptor_path, descriptor = restore_copy(source, manifest, backup_key=pc.c.db.copy_key(),
        target=target, new_device=str(uuid4()), new_incarnation=str(uuid4()))
    assert descriptor["status"] == "requires-enrollment"
    assert descriptor["source_device"] == pc.identity.device_id
    assert descriptor["preserved_database"] == target.name
    assert descriptor_path.is_file() and target.is_file()
    with target.open("rb") as handle:
        assert handle.read(16) != b"SQLite format 3\x00"


def test_saved_candidate_is_restored_without_posting_money(devices, tmp_path):
    from lightning.sync.journal.capture import JournalCapture
    _, pc = devices
    capture = JournalCapture(pc)
    identifier = capture.candidate(groups(pc), namespace="bank:dummy", source_id="statement-1", batch="dummy-import")
    source = tmp_path / "backup.db"
    manifest = backup(pc, source)
    with pc.c.db.transaction():
        pc.c.db.execute("DELETE FROM journal_candidates")
        pc.c.db.execute("DELETE FROM journal_candidate_inputs")
    before = pc.balances()
    assert recover_queue(pc, source, manifest, backup_key=pc.c.db.copy_key()) == 0
    assert capture.waiting()[0]["id"] == identifier
    assert pc.balances() == before


def _fresh_replica(home, tmp_path, authority=None):
    from lightning.bootstrap import build
    from lightning.sync.identity import load_or_create
    from lightning.sync.journal.device import JournalDevice
    from lightning.sync.journal.finance import attach
    from lightning.sync.journal.snapshots import checkpoint_replica

    identity = load_or_create(tmp_path / "fresh-identity", "Fresh recovery device")
    incarnation = str(uuid4())
    path = tmp_path / "fresh-replica.db"
    checkpoint_replica(home.store, path, home.identity.sign, device=identity.device_id,
                       incarnation=incarnation, origin_key=identity.public_key)
    container = build(path, key=home.store.db.copy_key(), experimental_journal=True)
    store = attach(container)
    if authority is not None:
        authority.bind(store)
    home.home.approve_origin(identity.device_id, incarnation, identity.public_key)
    return container, JournalDevice(store, identity)


def _authority(home, tmp_path):
    import os
    from cryptography.hazmat.primitives.asymmetric import ec
    from lightning.sync.journal.authority import AuthorityMemory
    from lightning.sync.journal.codec import seal
    from lightning.sync.journal.owner import OwnerCredential

    owner = OwnerCredential(ec.generate_private_key(ec.SECP256R1()))
    config = home.store.config
    wire = seal(dict(type="authority-enrollment", version=1, profile=config["profile"],
                     generation=config["generation"], home=config["device"], home_key=config["home_key"],
                     owner_key=owner.public_key), owner.sign)
    authority = AuthorityMemory.enroll(tmp_path / "recovery-authority.db", wire)
    authority.bind(home.store)
    return owner, authority


def test_restore_reproposes_dependency_chain_once_and_applies_effect_once(devices, tmp_path):
    home, old = devices
    _, authority = _authority(home, tmp_path)
    first = old.save(groups(old, "-10"))
    record = unpack(first)["body"]["record"]
    second = old.save({"details": dict(counterparty="", notes="recovered edit", description="")}, record=record)
    source = tmp_path / "old-device.db"
    manifest = backup(old, source)
    container, fresh = _fresh_replica(home, tmp_path, authority)
    try:
        assert repropose_copy(fresh, source, manifest, backup_key=container.db.copy_key()) == {
            "reproposed": 2, "already_decided": 0, "held": 0}
        pending = [unpack(wire)["body"] for wire in fresh.store.pending()]
        assert len(pending) == 2
        assert pending[1]["dependencies"] == [pending[0]["origin"]]
        assert repropose_copy(fresh, source, manifest, backup_key=container.db.copy_key()) == {
            "reproposed": 2, "already_decided": 0, "held": 0}
        assert container.db.scalar("SELECT next_seq FROM journal_meta") == 3
        fresh.sync_with(home.home)
        assert next(item["balance"] for item in home.balances() if item["name"] == "Bank") == 990
        assert fresh.store.pending() == []
    finally:
        container.db.close()
        authority.close()


def test_restore_reproposal_keeps_stale_base_for_home_review(devices, tmp_path):
    home, old = devices
    _, authority = _authority(home, tmp_path)
    added = home.save(groups(home, "-10"))
    record = unpack(added)["body"]["record"]
    old.sync_with(home.home)
    old_base = old.store.record(record)["tokens"]["details"]
    home.save({"details": dict(counterparty="", notes="newer home edit", description="")}, record=record)
    stale = old.save({"details": dict(counterparty="", notes="offline stale edit", description="")}, record=record)
    original = unpack(stale)["body"]
    assert original["bases"]["details"] == old_base
    source = tmp_path / "old-device.db"
    manifest = backup(old, source)
    container, fresh = _fresh_replica(home, tmp_path, authority)
    try:
        repropose_copy(fresh, source, manifest, backup_key=container.db.copy_key())
        recovered = unpack(fresh.store.pending()[0])["body"]
        assert recovered["bases"]["details"] == old_base
        fresh.sync_with(home.home)
        assert home.home.status(origin_id(recovered["origin"]))["status"] == "review"
        assert home.store.record(record)["groups"]["details"]["notes"] == "newer home edit"
    finally:
        container.db.close()
        authority.close()


def test_recovery_after_home_move_verifies_pinned_old_receipts(devices, tmp_path):
    import os
    from cryptography.hazmat.primitives.asymmetric import ec
    from lightning.sync.journal.authority import transfer_home_state
    from lightning.sync.journal.codec import seal
    from lightning.sync.journal.home import JournalHome
    from lightning.sync.journal.owner import OwnerCredential
    from lightning.sync.journal.authority import AuthorityMemory

    home, old = devices
    owner = OwnerCredential(ec.generate_private_key(ec.SECP256R1()))
    config = home.store.config
    enrollment = seal(dict(type="authority-enrollment", version=1, profile=config["profile"],
        generation=config["generation"], home=config["device"], home_key=config["home_key"],
        owner_key=owner.public_key), owner.sign)
    controls = [AuthorityMemory.enroll(tmp_path / "home-authority.db", enrollment),
                AuthorityMemory.enroll(tmp_path / "old-authority.db", enrollment)]
    controls[0].bind(home.store)
    controls[1].bind(old.store)
    home.save(groups(home, "-10"))
    old.sync_with(home.home)
    queued = old.save(groups(old, "-8"))
    source = tmp_path / "pre-move-backup.db"
    manifest = backup(old, source)

    controls[0].freeze(home.store)
    transfer_home_state(home.store, old.store)
    transition = seal(dict(profile=config["profile"], previous=config["generation"], generation=str(uuid4()),
        home=old.identity.device_id, home_key=old.identity.public_key, owner_key=owner.public_key,
        version=2, mode="move", nonce=os.urandom(32).hex(), cutoff=old.store.cursor()), owner.sign)
    prepared = controls[1].prepare(old.store, transition, old.identity.sign)
    retired = controls[0].retire(home.store, transition, prepared, home.identity.sign)
    controls[1].activate_move(old.store, transition, prepared, retired, old_home_key=home.identity.public_key)
    old.home = JournalHome(old.store, old.identity.sign)
    old.flush_home()
    assert old.store.db.scalar("SELECT wire FROM journal_outbox WHERE seq=1") == queued

    container, fresh = _fresh_replica(old, tmp_path, controls[1])
    try:
        counts = repropose_copy(fresh, source, manifest, backup_key=container.db.copy_key())
        assert counts == {"reproposed": 0, "already_decided": 1, "held": 0}
        assert fresh.store.pending() == []
        assert fresh.store.cursor() == old.store.cursor()
    finally:
        container.db.close()
        for control in controls:
            control.close()
