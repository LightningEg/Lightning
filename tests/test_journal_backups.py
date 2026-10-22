"""Encrypted local queue recovery never rewinds money, identity or origin counter."""
import json

import pytest

from test_journal_finance import devices, groups
from lightning.sync.journal.backups import create, recover_queue
from lightning.sync.journal.codec import JournalError, seal, unpack


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
