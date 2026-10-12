import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from lightning.runtime.instance import InstanceAlreadyRunning, InstanceLock
from lightning.runtime.paths import discover_profiles
from lightning.runtime.session import ProfileError, ProfileSession, write_slot


PASSWORD = "a correct long passphrase"
NEW_PASSWORD = "another correct long passphrase"
QUESTION = "What was the name of your first school?"
ANSWER = "El Orman"


def created(tmp_path):
    session = ProfileSession(tmp_path / "Documents" / "Lightning")
    pending = session.prepare("Home", PASSWORD, PASSWORD, QUESTION, ANSWER)
    session.confirm(session.pending.recovery)
    return session, pending


def test_setup_is_explicit_and_encrypted_and_reopens(tmp_path):
    session = ProfileSession(tmp_path / "profiles")
    pending = session.prepare("Home", PASSWORD, PASSWORD, QUESTION, ANSWER)
    assert not session.root.exists()
    with pytest.raises(ProfileError, match="recovery key shown"):
        session.confirm("")
    session.confirm(session.pending.recovery)
    path = session.paths.db_path
    session.container.settings.set("test_marker", "private data")
    with pytest.raises(InstanceAlreadyRunning):
        InstanceLock(session.paths.lock_path).acquire()
    assert b"private data" not in path.read_bytes()
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("SELECT * FROM sqlite_master").fetchall()
    old_container = session.container
    session.close()
    with pytest.raises(RuntimeError, match="closed"):
        old_container.db.conn
    session.unlock(str(path), PASSWORD)
    assert session.container.settings.get("test_marker") == "private data"
    assert list(session.paths.backups_dir.glob("*.db"))
    session.close()


def test_recovery_preserves_database_and_rejects_wrong_key(tmp_path):
    session, pending = created(tmp_path)
    path, slot = session.paths.db_path, session.paths.keys_path
    session.close()
    before_db, before_slot = path.read_bytes(), slot.read_bytes()
    with pytest.raises(ProfileError):
        session.recover(str(path), "bad key", ANSWER, NEW_PASSWORD, NEW_PASSWORD)
    assert slot.read_bytes() == before_slot
    session.retry_at = 0
    session.recover(str(path), pending.recovery, ANSWER, NEW_PASSWORD, NEW_PASSWORD)
    assert path.read_bytes() == before_db
    assert slot.read_bytes() != before_slot
    with pytest.raises(ProfileError, match="incorrect"):
        session.unlock(str(path), PASSWORD)
    session.retry_at = 0
    session.unlock(str(path), NEW_PASSWORD)
    session.close()


def test_missing_slot_recovers_and_changes_password(tmp_path):
    session, pending = created(tmp_path)
    path, slot = session.paths.db_path, session.paths.keys_path
    session.close()
    slot.unlink()
    session.recover(str(path), pending.recovery, ANSWER, PASSWORD, PASSWORD)
    session.unlock(str(path), PASSWORD)
    session.change_password(ANSWER, NEW_PASSWORD, NEW_PASSWORD)
    session.close()
    session.unlock(str(path), NEW_PASSWORD)
    session.close()


def test_profiles_stay_separate_and_do_not_overwrite(tmp_path):
    session, first = created(tmp_path)
    first_path = session.paths.db_path
    session.close()
    second = session.prepare("Home", NEW_PASSWORD, NEW_PASSWORD, QUESTION, ANSWER)
    session.confirm(session.pending.recovery)
    assert first_path != session.paths.db_path
    assert len(discover_profiles(session.root)) == 2
    assert first.paths.profile.sequence == 1
    assert second.paths.profile.sequence == 2
    session.close()


def test_plaintext_and_backups_not_opened_as_live_profiles(tmp_path):
    source = tmp_path / "old.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE example (id)")
    before = source.read_bytes()
    session = ProfileSession(tmp_path / "profiles")
    with pytest.raises(ProfileError, match="legacy"):
        session.unlock(str(source), PASSWORD)
    assert source.read_bytes() == before
    assert not (tmp_path / ".old.db.lightning").exists()
    session, _ = created(tmp_path)
    snapshot = session.container.backup_now()
    session.close()
    with pytest.raises(ProfileError, match="backup"):
        session.unlock(str(snapshot), PASSWORD)


def test_pending_expires_and_slot_publication_is_non_destructive(tmp_path):
    session = ProfileSession(tmp_path / "profiles")
    pending = session.prepare("Home", PASSWORD, PASSWORD, QUESTION, ANSWER)
    pending.expires = 0
    with pytest.raises(ProfileError, match="expired"):
        session.confirm(session.pending.recovery)
    assert not session.root.exists()
    slot = tmp_path / "keys.json"
    write_slot(slot, {"old": True})
    with pytest.raises(FileExistsError):
        write_slot(slot, {"new": True})
    assert json.loads(slot.read_text()) == {"old": True}
    assert not list(tmp_path.glob("*.partial"))


def test_failed_setup_is_not_discovered_or_reused(tmp_path, monkeypatch):
    from lightning.runtime import session as module
    session = ProfileSession(tmp_path / "profiles")
    pending = session.prepare("Home", PASSWORD, PASSWORD, QUESTION, ANSWER)
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic disk failure")
    monkeypatch.setattr(module, "build", fail)
    with pytest.raises(RuntimeError):
        session.confirm(session.pending.recovery)
    assert not discover_profiles(session.root)
    assert pending.paths.keys_path.exists()
    with InstanceLock(pending.paths.lock_path):
        pass
    next_pending = session.prepare("Home", PASSWORD, PASSWORD, QUESTION, ANSWER)
    assert next_pending.paths.profile.sequence == 2


def test_restore_backup_keeps_source_and_pre_restore_copy_and_reopens(tmp_path):
    session, _ = created(tmp_path)
    live = session.paths.db_path
    backups_dir = session.paths.backups_dir
    slot = session.paths.keys_path
    session.container.settings.set("restore_marker", "old checkpoint")
    selected = session.container.backup_now()
    source_before = selected.read_bytes()
    session.container.settings.set("restore_marker", "current live")
    live_before = live.read_bytes()
    slot_before = slot.read_bytes()
    session.close()

    session.restore_backup(str(live), str(selected), PASSWORD)
    assert session.container is None
    assert session.lock is None
    assert selected.read_bytes() == source_before
    preserved = list(backups_dir.glob(".lightning-restore-source-*.db"))
    assert len(preserved) == 1
    assert preserved[0].read_bytes() == source_before
    assert slot.read_bytes() == slot_before
    assert live.read_bytes() != live_before
    assert len(list(backups_dir.glob("*_upgrade_*.db"))) >= 1
    session.unlock(str(live), PASSWORD)
    assert session.container.settings.get("restore_marker") == "old checkpoint"
    from lightning.database.backup import backup
    backup(session.container.db, backups_dir, keep=1)
    assert not selected.exists()
    assert preserved[0].read_bytes() == source_before
    session.close()
    fresh = ProfileSession(session.root)
    fresh.unlock(str(live), PASSWORD)
    assert fresh.container.settings.get("restore_marker") == "old checkpoint"
    fresh.close()


def test_restore_manifest_publication_falls_back_when_hard_links_are_forbidden(tmp_path, monkeypatch):
    import errno
    from lightning.runtime import restore as restore_module
    from lightning.runtime.restore import RestoreManifest

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "current")
    selected = session.container.backup_now()
    session.close()

    def deny_hard_links(*args, **kwargs):
        raise OSError(errno.EPERM, "hard links are unavailable")

    monkeypatch.setattr(restore_module.os, "link", deny_hard_links)
    session.restore_backup(str(live), str(selected), PASSWORD)

    (marker,) = paths.data_dir.glob(".lightning-restore-*.state")
    assert RestoreManifest.from_bytes(marker.read_bytes()).state == "COMPLETE"
    assert not list(paths.data_dir.glob("*.partial"))
    session.unlock(str(live), PASSWORD)
    assert session.container.settings.get("restore_marker") == "current"
    session.close()


@pytest.mark.parametrize("failure_point", [
    "before_initialize", "after_initialize", "mismatched_accepted",
])
def test_abandoned_restore_with_unprepared_control_store_is_retired(
    tmp_path, monkeypatch, failure_point
):
    from lightning.database.promotion import SqlitePromotionJournalStore
    from lightning.runtime.restore import RestoreManifest

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "current")
    selected = session.container.backup_now()
    session.close()
    live_before = live.read_bytes()

    initialize = SqlitePromotionJournalStore.initialize_accepted

    def fail_during_initialization(store, *args, **kwargs):
        if failure_point == "before_initialize":
            raise OSError("injected failure before accepted checkpoint initialization")
        result = initialize(store, *args, **kwargs)
        if failure_point == "mismatched_accepted":
            with sqlite3.connect(store.path) as connection:
                connection.execute(
                    "UPDATE promotion_control SET accepted_checkpoint_id=?, accepted_sha256=? "
                    "WHERE singleton=1",
                    ("other-valid-checkpoint", "e" * 64),
                )
            raise OSError("injected mismatched accepted checkpoint")
        raise OSError("injected failure after accepted checkpoint initialization")

    monkeypatch.setattr(SqlitePromotionJournalStore, "initialize_accepted", fail_during_initialization)
    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    monkeypatch.setattr(SqlitePromotionJournalStore, "initialize_accepted", initialize)

    (marker,) = paths.data_dir.glob(".lightning-restore-*.state")
    manifest = RestoreManifest.from_bytes(marker.read_bytes())
    control = paths.data_dir / f".lightning-restore-{manifest.operation_id}.sqlite"
    assert control.is_file()
    assert manifest.state == "PENDING"
    if failure_point == "before_initialize":
        store = SqlitePromotionJournalStore(control)
        state = store.read_state()
        assert state.accepted is None and state.journal is None
    else:
        store = SqlitePromotionJournalStore(control)
        state = store.read_state()
        assert state.journal is None
        if failure_point == "mismatched_accepted":
            assert state.accepted.checkpoint_id == "other-valid-checkpoint"
            session.retry_at = 0.0
            with pytest.raises(ProfileError, match="unprepared control state disagree"):
                session.resume_interrupted_restore(str(live), PASSWORD)
            assert RestoreManifest.from_bytes(marker.read_bytes()).state == "PENDING"
            assert live.read_bytes() == live_before
            return
        assert state.accepted is not None

    session.retry_at = 0.0
    session.resume_interrupted_restore(str(live), PASSWORD)
    assert RestoreManifest.from_bytes(marker.read_bytes()).state == "ABANDONED"
    assert live.read_bytes() == live_before
    session.unlock(str(live), PASSWORD)
    assert session.container.settings.get("restore_marker") == "current"
    if failure_point == "after_initialize":
        session.close()
        with sqlite3.connect(control) as connection:
            connection.execute(
                "UPDATE promotion_control SET accepted_checkpoint_id=?, accepted_sha256=? "
                "WHERE singleton=1",
                ("other-valid-checkpoint", "e" * 64),
            )
        fresh = ProfileSession(session.root)
        with pytest.raises(ProfileError, match="control state|repair"):
            fresh.unlock(str(live), PASSWORD)
        return
    session.close()


def test_resume_does_not_recreate_missing_control_singleton(tmp_path, monkeypatch):
    from lightning.database.promotion import SqlitePromotionJournalStore
    from lightning.runtime.restore import RestoreManifest

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    selected = session.container.backup_now()
    session.close()
    live_before = live.read_bytes()

    initialize = SqlitePromotionJournalStore.initialize_accepted

    def fail_after_initialize(store, *args, **kwargs):
        initialize(store, *args, **kwargs)
        raise OSError("injected interruption after accepted checkpoint initialization")

    monkeypatch.setattr(SqlitePromotionJournalStore, "initialize_accepted", fail_after_initialize)
    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    monkeypatch.setattr(SqlitePromotionJournalStore, "initialize_accepted", initialize)

    (marker,) = paths.data_dir.glob(".lightning-restore-*.state")
    manifest = RestoreManifest.from_bytes(marker.read_bytes())
    control = paths.data_dir / f".lightning-restore-{manifest.operation_id}.sqlite"
    with sqlite3.connect(control) as connection:
        connection.execute("DELETE FROM promotion_control WHERE singleton=1")
        assert connection.execute("SELECT COUNT(*) FROM promotion_control").fetchone()[0] == 0

    session.retry_at = 0.0
    with pytest.raises(ProfileError, match="readable matching journal|locked"):
        session.resume_interrupted_restore(str(live), PASSWORD)
    assert RestoreManifest.from_bytes(marker.read_bytes()).state == "PENDING"
    assert live.read_bytes() == live_before
    with sqlite3.connect(control) as connection:
        assert connection.execute("SELECT COUNT(*) FROM promotion_control").fetchone()[0] == 0


def test_completed_restore_blocks_if_previous_checkpoint_is_missing(tmp_path):
    session, _ = created(tmp_path)
    live, data_dir = session.paths.db_path, session.paths.data_dir
    selected = session.container.backup_now()
    session.close()
    session.restore_backup(str(live), str(selected), PASSWORD)
    previous = next(data_dir.glob(".lightning-restore-*.previous.db"))
    previous.unlink()
    fresh = ProfileSession(session.root)
    with pytest.raises(ProfileError, match="pre-restore checkpoint"):
        fresh.unlock(str(live), PASSWORD)


def test_completed_restore_blocks_if_previous_checkpoint_is_corrupt(tmp_path):
    session, _ = created(tmp_path)
    live, data_dir = session.paths.db_path, session.paths.data_dir
    selected = session.container.backup_now()
    session.close()
    session.restore_backup(str(live), str(selected), PASSWORD)
    previous = next(data_dir.glob(".lightning-restore-*.previous.db"))
    with previous.open("r+b") as handle:
        handle.seek(128)
        byte = handle.read(1)
        handle.seek(128)
        handle.write(bytes([byte[0] ^ 0x40]))
    fresh = ProfileSession(session.root)
    with pytest.raises(ProfileError, match="does not match its journal"):
        fresh.unlock(str(live), PASSWORD)


@pytest.mark.parametrize("evidence", [
    "source_copy_missing", "source_copy_corrupt", "pre_restore_missing",
    "pre_restore_corrupt", "source_backup_corrupt", "malformed_manifest",
])
def test_completed_restore_blocks_when_manifest_evidence_is_missing_or_corrupt(tmp_path, evidence):
    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    selected = session.container.backup_now()
    session.close()
    session.restore_backup(str(live), str(selected), PASSWORD)
    manifest = next(paths.data_dir.glob(".lightning-restore-*.state"))
    if evidence.startswith("source_copy"):
        protected = next(paths.backups_dir.glob(".lightning-restore-source-*.db"))
        if evidence.endswith("missing"):
            protected.unlink()
        else:
            with protected.open("r+b") as handle:
                handle.seek(128)
                byte = handle.read(1)
                handle.seek(128)
                handle.write(bytes([byte[0] ^ 0x20]))
    elif evidence.startswith("pre_restore"):
        pre_restore = next(paths.backups_dir.glob("*_upgrade_*.db"))
        if evidence.endswith("missing"):
            pre_restore.unlink()
        else:
            with pre_restore.open("r+b") as handle:
                handle.seek(128)
                byte = handle.read(1)
                handle.seek(128)
                handle.write(bytes([byte[0] ^ 0x20]))
    elif evidence == "source_backup_corrupt":
        with selected.open("r+b") as handle:
            handle.seek(128)
            byte = handle.read(1)
            handle.seek(128)
            handle.write(bytes([byte[0] ^ 0x20]))
    else:
        manifest.write_bytes(b'{"schema_version":1,"state":"COMPLETE"}')
    fresh = ProfileSession(session.root)
    with pytest.raises(ProfileError, match="manifest|source copy|retained restore backup"):
        fresh.unlock(str(live), PASSWORD)


def test_restore_manifest_rejects_unknown_schema_and_noncanonical_names():
    from dataclasses import replace
    from lightning.runtime.restore import RestoreManifest

    digest = "a" * 64
    manifest = RestoreManifest(
        state="PENDING", operation_id="1" * 32, profile_id="profile-1",
        live_name="profile.db", old_checkpoint_id="restore-base-" + digest[:32],
        old_sha256=digest, candidate_name="candidate.partial",
        new_checkpoint_id="restore-" + "2" * 32, candidate_sha256="b" * 64,
        previous_name=f".lightning-restore-{'1' * 32}.previous.db",
        source_backup_name="profile_backup_2030-01-01_001_1234abcd.db",
        source_sha256="c" * 64,
        source_copy_name=f".lightning-restore-source-{'1' * 32}.db",
        source_copy_sha256="c" * 64,
        pre_restore_name="profile_upgrade_2030-01-01_001_1234abcd.db",
        pre_restore_sha256="d" * 64,
    )
    record = json.loads(manifest.to_bytes())
    record["schema_version"] = 2
    with pytest.raises(ValueError, match="Unsupported"):
        RestoreManifest.from_bytes(json.dumps(record).encode())
    with pytest.raises(ValueError, match="sibling basenames"):
        replace(manifest, candidate_name="../candidate.partial")


def test_unlock_verifies_retained_encrypted_copies_with_profile_key(tmp_path, monkeypatch):
    from lightning.runtime.restore import EncryptedBackupRestorer

    session, _ = created(tmp_path)
    live = session.paths.db_path
    selected = session.container.backup_now()
    session.close()
    session.restore_backup(str(live), str(selected), PASSWORD)

    original_verify = EncryptedBackupRestorer._verify_file

    def refuse_protected_source(cls, path, key):
        if path.name.startswith(".lightning-restore-source-"):
            raise ValueError("injected encrypted-copy verification failure")
        return original_verify(path, key)

    monkeypatch.setattr(EncryptedBackupRestorer, "_verify_file",
                        classmethod(refuse_protected_source))
    with pytest.raises(ProfileError, match="retained restore backup"):
        ProfileSession(session.root).unlock(str(live), PASSWORD)


def test_restore_completed_marker_without_journal_blocks_unlock(tmp_path):
    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "before")
    selected = session.container.backup_now()
    session.container.settings.set("restore_marker", "after")
    session.close()
    session.restore_backup(str(live), str(selected), PASSWORD)
    for journal in paths.data_dir.glob(".lightning-restore-*.sqlite"):
        journal.unlink()
    fresh = ProfileSession(session.root)
    with pytest.raises(ProfileError, match="manifest has no complete matching journal"):
        fresh.unlock(str(live), PASSWORD)


@pytest.mark.parametrize("damage", ["wrong_key", "corrupt", "newer_schema"])
def test_restore_rejects_unusable_backup_without_changing_live_or_source(tmp_path, damage):
    from lightning.database.connection import Database
    from lightning.database.staging import stage_database

    session, pending = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "keep current")
    session.close()
    if damage == "wrong_key":
        # Produce a structurally valid ciphertext backup encrypted under a
        # different key, then give it an exact in-profile backup filename.
        staged = stage_database(live, paths.data_dir, destination_key=b"z" * 32,
                                source_key=pending.key)
        candidate = staged.path
    else:
        staged = stage_database(live, paths.data_dir, destination_key=pending.key,
                                source_key=pending.key)
        candidate = staged.path
        if damage == "corrupt":
            with candidate.open("r+b") as handle:
                handle.seek(128)
                value = handle.read(1)
                handle.seek(128)
                handle.write(bytes([value[0] ^ 0x80]))
        else:
            db = Database(candidate, key=pending.key)
            try:
                db.execute("UPDATE schema_migrations SET version=999 WHERE version=(SELECT MAX(version) FROM schema_migrations)")
            finally:
                db.close()
    backup_path = paths.backups_dir / f"{live.stem}_backup_2030-01-01_999_1234abcd.db"
    os.replace(candidate, backup_path)
    source_before, live_before, slot_before = backup_path.read_bytes(), live.read_bytes(), paths.keys_path.read_bytes()
    with pytest.raises(ProfileError, match="damaged|another key|newer"):
        session.restore_backup(str(live), str(backup_path), PASSWORD)
    assert backup_path.read_bytes() == source_before
    assert live.read_bytes() == live_before
    assert paths.keys_path.read_bytes() == slot_before
    with InstanceLock(paths.lock_path):
        pass


def test_restore_rejects_live_sidecars_without_touching_any_database(tmp_path):
    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    selected = session.container.backup_now()
    selected_before, live_before = selected.read_bytes(), live.read_bytes()
    session.close()
    sidecar = Path(str(live) + "-wal")
    sidecar.write_bytes(b"uncheckpointed evidence")
    with pytest.raises(ProfileError, match="sidecars"):
        session.restore_backup(str(live), str(selected), PASSWORD)
    assert selected.read_bytes() == selected_before
    assert live.read_bytes() == live_before
    assert sidecar.read_bytes() == b"uncheckpointed evidence"
    sidecar.unlink()


def test_restore_rejects_backup_sidecars_and_preserves_both_files(tmp_path):
    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    selected = session.container.backup_now()
    source_before, live_before = selected.read_bytes(), live.read_bytes()
    session.close()
    sidecar = Path(str(selected) + "-journal")
    sidecar.write_bytes(b"backup journal evidence")
    with pytest.raises(ProfileError, match="sidecars"):
        session.restore_backup(str(live), str(selected), PASSWORD)
    assert selected.read_bytes() == source_before
    assert live.read_bytes() == live_before
    assert sidecar.read_bytes() == b"backup journal evidence"
    sidecar.unlink()


def test_interrupted_restore_marker_blocks_fresh_unlock(tmp_path, monkeypatch):
    from lightning.database.promotion import CandidatePromotionService, PromotionBlocked

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "current")
    selected = session.container.backup_now()
    session.close()

    def fail_after_prepare(self, **kwargs):
        raise PromotionBlocked("injected publication failure")

    monkeypatch.setattr(CandidatePromotionService, "promote", fail_after_prepare)
    with pytest.raises(ProfileError, match="repair|failed safely"):
        session.restore_backup(str(live), str(selected), PASSWORD)
    # A missing journal cannot make an interrupted operation look standalone.
    for journal in paths.data_dir.glob(".lightning-restore-*.sqlite"):
        journal.unlink()
    fresh = ProfileSession(session.root)
    with pytest.raises(ProfileError, match="interrupted restore"):
        fresh.unlock(str(live), PASSWORD)
    assert not fresh.container


def test_abandoned_restore_intent_is_retired_with_evidence_preserved(tmp_path, monkeypatch):
    """A crash after PENDING but before journal creation leaves an untouched live DB."""
    from lightning.runtime.restore import EncryptedBackupRestorer, RestoreManifest

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "current")
    selected = session.container.backup_now()
    session.close()
    live_before = live.read_bytes()

    publish = EncryptedBackupRestorer._write_restore_manifest

    def publish_then_crash(path, manifest, *, replace_existing=False):
        publish(path, manifest, replace_existing=replace_existing)
        if manifest.state == "PENDING":
            raise OSError("injected crash after durable intent")

    monkeypatch.setattr(EncryptedBackupRestorer, "_write_restore_manifest",
                        staticmethod(publish_then_crash))
    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    (marker,) = paths.data_dir.glob(".lightning-restore-*.state")
    manifest = RestoreManifest.from_bytes(marker.read_bytes())
    assert manifest.state == "PENDING"
    assert not (paths.data_dir / f".lightning-restore-{manifest.operation_id}.sqlite").exists()
    source_copy = paths.backups_dir / manifest.source_copy_name
    source_before = source_copy.read_bytes()

    # Recovery classifies the operation as abandoned without discarding its audit copies.
    session.retry_at = 0.0
    session.resume_interrupted_restore(str(live), PASSWORD)
    monkeypatch.setattr(EncryptedBackupRestorer, "_write_restore_manifest", staticmethod(publish))
    repaired = RestoreManifest.from_bytes(marker.read_bytes())
    assert repaired.state == "ABANDONED"
    assert live.read_bytes() == live_before
    assert source_copy.read_bytes() == source_before
    assert selected.exists()

    session.unlock(str(live), PASSWORD)
    assert session.container.settings.get("restore_marker") == "current"
    session.container.settings.set("restore_marker", "edited after repair")
    session.close()
    fresh = ProfileSession(session.root)
    fresh.unlock(str(live), PASSWORD)
    assert fresh.container.settings.get("restore_marker") == "edited after repair"
    later_backup = fresh.container.backup_now()
    fresh.close()
    fresh.restore_backup(str(live), str(later_backup), PASSWORD)
    fresh.unlock(str(live), PASSWORD)
    assert fresh.container.settings.get("restore_marker") == "edited after repair"
    fresh.close()


def test_abandoned_restore_intent_with_changed_live_database_stays_locked(tmp_path, monkeypatch):
    from lightning.runtime.restore import EncryptedBackupRestorer, RestoreManifest

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    selected = session.container.backup_now()
    session.close()

    publish = EncryptedBackupRestorer._write_restore_manifest

    def publish_then_crash(path, manifest, *, replace_existing=False):
        publish(path, manifest, replace_existing=replace_existing)
        if manifest.state == "PENDING":
            raise OSError("injected crash after durable intent")

    monkeypatch.setattr(EncryptedBackupRestorer, "_write_restore_manifest",
                        staticmethod(publish_then_crash))
    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    (marker,) = paths.data_dir.glob(".lightning-restore-*.state")
    manifest = RestoreManifest.from_bytes(marker.read_bytes())
    source_copy = paths.backups_dir / manifest.source_copy_name
    source_before = source_copy.read_bytes()
    live.write_bytes(live.read_bytes() + b"changed")

    session.retry_at = 0.0
    with pytest.raises(ProfileError, match="live database changed"):
        session.resume_interrupted_restore(str(live), PASSWORD)
    assert RestoreManifest.from_bytes(marker.read_bytes()).state == "PENDING"
    assert source_copy.read_bytes() == source_before
    assert selected.exists()


@pytest.mark.parametrize("boundary", ["P1", "P2", "P3", "P4"])
def test_resume_interrupted_restore_advances_durable_phases(tmp_path, monkeypatch, boundary):
    from lightning.database.promotion import PromotionPhase, SqlitePromotionJournalStore
    from lightning.runtime.restore import EncryptedBackupRestorer

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "current")
    selected = session.container.backup_now()
    session.close()

    def inject_once(method, predicate=lambda *args, **kwargs: True):
        original = getattr(SqlitePromotionJournalStore, method)
        tripped = {"value": False}

        def wrapper(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            if not tripped["value"] and predicate(*args, **kwargs):
                tripped["value"] = True
                raise OSError(f"injected {boundary} interruption")
            return result

        monkeypatch.setattr(SqlitePromotionJournalStore, method, wrapper)
        return tripped

    if boundary == "P1":
        inject_once("prepare")
    elif boundary == "P2":
        inject_once("advance", lambda _old, new: new.phase is PromotionPhase.PREVIOUS_PROTECTED)
    elif boundary == "P3":
        if os.name == "nt":
            from lightning.database.promotion_windows import WindowsPromotionFileOps as FileOps
        else:
            from lightning.database.promotion import PosixPromotionFileOps as FileOps
        original = FileOps.atomic_replace
        tripped = {"value": False}

        def replace_then_fail(self, source, destination):
            result = original(self, source, destination)
            if not tripped["value"]:
                tripped["value"] = True
                raise OSError("injected P3 interruption")
            return result

        monkeypatch.setattr(FileOps, "atomic_replace", replace_then_fail)
    else:
        inject_once("commit_authority")

    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    assert session.container is None and session.lock is None
    # The interruption hook is one-shot; recovery uses the durable journal and
    # verifies encrypted candidate/previous files before advancing further.
    if boundary == "P3":
        monkeypatch.setattr(FileOps, "atomic_replace", original)
    session.retry_at = 0.0
    EncryptedBackupRestorer(session).resume_interrupted_restore(str(live), PASSWORD)
    assert session.container is None and session.lock is None
    assert len(list(paths.data_dir.glob(".lightning-restore-*.state"))) == 1
    session.unlock(str(live), PASSWORD)
    assert session.container.settings.get("restore_marker") == "current"
    session.close()


@pytest.mark.skipif(os.name == "nt", reason="Process-kill phase injection uses the POSIX adapter")
@pytest.mark.parametrize("boundary", ["P1", "P2", "P3", "P4"])
def test_process_kill_restore_recovery_preserves_evidence(tmp_path, boundary):
    """A fresh interpreter resumes each durable phase after abrupt process exit."""
    import hashlib

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "before restore")
    selected = session.container.backup_now()
    session.container.settings.set("restore_marker", "current live")
    session.close()
    old_live_hash = hashlib.sha256(live.read_bytes()).hexdigest()
    root = str(session.root)
    live_name, source_name = str(live), str(selected)

    crash_code = r'''
import os, sys
from lightning.database.promotion import PromotionPhase, SqlitePromotionJournalStore
from lightning.database.promotion import PosixPromotionFileOps
from lightning.runtime.session import ProfileSession
root, live, source, password, boundary = sys.argv[1:]
if boundary == "P1":
    original = SqlitePromotionJournalStore.prepare
    def interrupt(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        os._exit(73)
    SqlitePromotionJournalStore.prepare = interrupt
elif boundary == "P2":
    original = SqlitePromotionJournalStore.advance
    def interrupt(self, old, new):
        result = original(self, old, new)
        if new.phase is PromotionPhase.PREVIOUS_PROTECTED:
            os._exit(73)
        return result
    SqlitePromotionJournalStore.advance = interrupt
elif boundary == "P3":
    original = PosixPromotionFileOps.atomic_replace
    def interrupt(self, source, destination):
        result = original(self, source, destination)
        os._exit(73)
    PosixPromotionFileOps.atomic_replace = interrupt
elif boundary == "P4":
    original = SqlitePromotionJournalStore.commit_authority
    def interrupt(self, journal):
        result = original(self, journal)
        os._exit(73)
    SqlitePromotionJournalStore.commit_authority = interrupt
else:
    raise AssertionError(boundary)
ProfileSession(root).restore_backup(live, source, password)
'''
    crashed = subprocess.run(
        [sys.executable, "-c", crash_code, root, live_name, source_name, PASSWORD, boundary],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=45,
    )
    assert crashed.returncode == 73, crashed.stderr
    marker = next(paths.data_dir.glob(".lightning-restore-*.state"))
    from lightning.runtime.restore import RestoreManifest
    manifest = RestoreManifest.from_bytes(marker.read_bytes())
    assert manifest.state == "PENDING"
    source_copy = paths.backups_dir / manifest.source_copy_name
    pre_restore = paths.backups_dir / manifest.pre_restore_name
    protected_hashes = {
        source_copy: hashlib.sha256(source_copy.read_bytes()).hexdigest(),
        pre_restore: hashlib.sha256(pre_restore.read_bytes()).hexdigest(),
    }

    resume_code = r'''
import sys
from lightning.runtime.session import ProfileSession
session = ProfileSession(sys.argv[1])
session.resume_interrupted_restore(sys.argv[2], sys.argv[3])
assert session.container is None and session.lock is None
'''
    resumed = subprocess.run(
        [sys.executable, "-c", resume_code, root, live_name, PASSWORD],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=45,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert RestoreManifest.from_bytes(marker.read_bytes()).state == "COMPLETE"
    for path, expected in protected_hashes.items():
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    previous = paths.data_dir / manifest.previous_name
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == old_live_hash
    fresh = ProfileSession(session.root)
    fresh.unlock(str(live), PASSWORD)
    assert fresh.container.settings.get("restore_marker") == "before restore"
    fresh.close()


def test_resume_rolls_back_a_hot_restore_journal(tmp_path, monkeypatch):
    """A crash inside a control-store transaction leaves a hot rollback journal.

    A read-only connection cannot roll it back, so recovery must open the store
    read-write under the held profile lock instead of staying locked forever.
    """
    from lightning.database.promotion import PromotionPhase, SqlitePromotionJournalStore
    from lightning.runtime.restore import EncryptedBackupRestorer

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "current")
    selected = session.container.backup_now()
    session.close()

    original = SqlitePromotionJournalStore.advance
    tripped = {"value": False}

    def advance_then_fail(self, expected, updated):
        result = original(self, expected, updated)
        if not tripped["value"] and updated.phase is PromotionPhase.PREVIOUS_PROTECTED:
            tripped["value"] = True
            raise OSError("injected P2 interruption")
        return result

    monkeypatch.setattr(SqlitePromotionJournalStore, "advance", advance_then_fail)
    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    monkeypatch.setattr(SqlitePromotionJournalStore, "advance", original)

    (control,) = paths.data_dir.glob(".lightning-restore-*.sqlite")
    crash = (
        "import os, sqlite3, sys\n"
        "c = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
        "c.execute('PRAGMA cache_size=1')\n"
        "c.execute('BEGIN IMMEDIATE')\n"
        "c.execute(\"UPDATE promotion_control SET journal_json='{}'\")\n"
        "c.execute('CREATE TABLE spill(x)')\n"
        "c.execute('INSERT INTO spill SELECT randomblob(200000) FROM (SELECT 1 UNION SELECT 2)')\n"
        "os._exit(0)\n"
    )
    subprocess.run([sys.executable, "-c", crash, str(control)], check=True)
    assert Path(str(control) + "-journal").exists(), "the crash must leave a hot journal"

    session.retry_at = 0.0
    EncryptedBackupRestorer(session).resume_interrupted_restore(str(live), PASSWORD)
    assert not Path(str(control) + "-journal").exists()
    session.unlock(str(live), PASSWORD)
    assert session.container.settings.get("restore_marker") == "current"
    session.close()


def test_restore_refused_by_file_adapter_leaves_profile_unlockable(tmp_path, monkeypatch):
    """A folder the adapter refuses (e.g. a OneDrive reparse point on Windows) is
    found before any restore intent is recorded, so nothing needs repair."""
    from lightning.database import promotion, promotion_windows

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "current")
    selected = session.container.backup_now()
    session.close()
    live_before = live.read_bytes()

    def refuse(self, directory):
        raise ValueError("Promotion directory path must not contain reparse points")

    monkeypatch.setattr(promotion.PosixPromotionFileOps, "__init__", refuse)
    monkeypatch.setattr(promotion_windows.WindowsPromotionFileOps, "__init__", refuse)
    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    assert live.read_bytes() == live_before
    assert not list(paths.data_dir.glob(".lightning-restore-*.state"))
    assert not list(paths.data_dir.glob(".lightning-restore-*.sqlite"))
    session.retry_at = 0.0
    session.unlock(str(live), PASSWORD)
    assert session.container.settings.get("restore_marker") == "current"
    session.close()


def test_restore_failing_before_its_record_removes_the_orphan_source_copy(tmp_path, monkeypatch):
    from lightning.runtime.restore import EncryptedBackupRestorer

    session, _ = created(tmp_path)
    live, paths = session.paths.db_path, session.paths
    session.container.settings.set("restore_marker", "current")
    selected = session.container.backup_now()
    session.close()

    def fail_write(path, manifest, *, replace_existing=False):
        raise OSError("injected failure before the restore record is written")

    monkeypatch.setattr(EncryptedBackupRestorer, "_write_restore_manifest", staticmethod(fail_write))
    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    assert not list(paths.backups_dir.glob(".lightning-restore-source-*.db"))
    assert selected.exists()
    session.retry_at = 0.0
    session.unlock(str(live), PASSWORD)
    assert session.container.settings.get("restore_marker") == "current"
    session.close()
