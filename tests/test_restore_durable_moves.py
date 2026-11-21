"""IT-2A2: restore's moves and discards are durable and in order: a copy goes before the record that
explains it, and a record moves after its files. On Windows the move is MOVEFILE_WRITE_THROUGH
(`tests/test_database_promotion_windows.py`); on POSIX a rename and an fsync of both folders."""

from __future__ import annotations

import os

import pytest

from lightning.runtime import restore
from lightning.runtime.session import ProfileError, ProfileSession
from tests.test_profile_session import PASSWORD, _killed_restore, created


def _record_steps(monkeypatch):
    steps = []
    move, discard = restore._durable_move, restore._durable_discard

    def recording_move(source, destination):
        if not destination.name.startswith(".lightning-discard-"):  # a discard's own move is its discard
            steps.append(("move", source.name))
        return move(source, destination)

    def recording_discard(path):
        if path.exists() or path.is_symlink():
            steps.append(("discard", path.name))
        return discard(path)
    monkeypatch.setattr(restore, "_durable_move", recording_move)
    monkeypatch.setattr(restore, "_durable_discard", recording_discard)
    return steps


def _kinds(steps):
    return [(kind, name.rsplit(".", 1)[-1] if not name.startswith(".lightning-restore-source-") else "copy")
            for kind, name in steps]


@pytest.mark.skipif(os.name == "nt", reason="POSIX half of the durable move")
def test_posix_durable_move_flushes_both_folders_and_never_replaces(tmp_path, monkeypatch):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "record.state").write_bytes(b"record")
    flushed = []
    monkeypatch.setattr(restore, "_fsync_folder", lambda folder: flushed.append(folder))
    restore._durable_move(tmp_path / "record.state", tmp_path / "evidence" / "record.state")
    assert set(flushed) == {tmp_path, tmp_path / "evidence"}
    (tmp_path / "other.state").write_bytes(b"other")
    with pytest.raises(FileExistsError):
        restore._durable_move(tmp_path / "other.state", tmp_path / "evidence" / "record.state")
    assert (tmp_path / "evidence" / "record.state").read_bytes() == b"record"


def test_durable_discard_moves_then_deletes(tmp_path, monkeypatch):
    target = tmp_path / ".lightning-restore-x.intent"
    target.write_bytes(b"intent")
    moved = []
    move = restore._durable_move
    monkeypatch.setattr(restore, "_durable_move", lambda s, d: (moved.append(d.name), move(s, d)))
    restore._durable_discard(target)
    assert not target.exists() and moved and moved[0].startswith(".lightning-discard-")
    assert not list(tmp_path.iterdir())
    restore._durable_discard(target)  # nothing there: nothing to do


def test_unlock_removes_the_copy_durably_before_its_intent(tmp_path, monkeypatch):
    session, live, paths, _selected, _ = _killed_restore(tmp_path, "copied")
    steps = _record_steps(monkeypatch)
    fresh = ProfileSession(session.root)
    fresh.unlock(str(live), PASSWORD)
    fresh.close()
    assert _kinds(steps) == [("discard", "copy"), ("discard", "intent")]


def test_unlock_sweeps_an_interrupted_copy_and_discard_leftovers(tmp_path):
    session, live, paths, _selected, _ = _killed_restore(tmp_path, "intent")
    intent = next(paths.data_dir.glob(".lightning-restore-*.intent"))
    operation = intent.name.removeprefix(".lightning-restore-").removesuffix(".intent")
    (paths.backups_dir / f".lightning-restore-source-{operation}.db.partial").write_bytes(b"half a copy")
    (paths.data_dir / ".lightning-discard-left").write_bytes(b"left by a cut discard")
    fresh = ProfileSession(session.root)
    fresh.unlock(str(live), PASSWORD)
    fresh.close()
    assert not list(paths.backups_dir.glob(".lightning-restore-source-*"))
    assert not list(paths.data_dir.glob(".lightning-discard-*"))
    assert not list(paths.data_dir.glob(".lightning-restore-*"))


def test_a_failed_restore_discards_its_copy_before_its_intent(tmp_path, monkeypatch):
    session, _ = created(tmp_path)
    live = session.paths.db_path
    selected = session.container.backup_now()
    session.close()
    write = restore.EncryptedBackupRestorer._write_restore_manifest

    def fail_record(path, record, *, replace_existing=False):
        if path.suffix == ".state":
            raise OSError("injected failure before the record")
        return write(path, record, replace_existing=replace_existing)
    monkeypatch.setattr(restore.EncryptedBackupRestorer, "_write_restore_manifest", staticmethod(fail_record))
    steps = _record_steps(monkeypatch)
    with pytest.raises(ProfileError):
        session.restore_backup(str(live), str(selected), PASSWORD)
    kinds = _kinds(steps)
    assert kinds == [("move", "copy"), ("discard", "copy"), ("discard", "intent")]  # copy moved in from .partial


def test_undo_moves_the_record_after_its_files(tmp_path, monkeypatch):
    session, live, paths, _selected, _ = _killed_restore(tmp_path, "accepted")
    steps = _record_steps(monkeypatch)
    fresh = ProfileSession(session.root)
    assert fresh.repair_interrupted_restore(str(live), PASSWORD) == "undone"
    moves = [name for kind, name in steps if kind == "move"]
    assert moves[-1].endswith(".state") and len(moves) >= 4
    assert sum(name.endswith(".state") for name in moves) == 1


def test_go_back_moves_the_record_with_durable_moves(tmp_path, monkeypatch):
    session, live, paths, _selected, _ = _killed_restore(tmp_path, "manifest")
    steps = _record_steps(monkeypatch)
    fresh = ProfileSession(session.root)
    fresh.retry_at = 0.0
    fresh.go_back_before_restore(str(live), PASSWORD)
    moved = [name for kind, name in steps if kind == "move"]
    assert any(name.endswith(".state") for name in moved) and any(name.endswith(".intent") for name in moved)
