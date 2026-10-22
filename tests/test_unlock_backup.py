"""2J: unlocking takes an automatic backup at most once a day, and checks the source database once."""
from __future__ import annotations

import lightning.database.backup as backup_module
import lightning.database.snapshot as snapshot_module
from lightning.database.backup import list_backups
from lightning.runtime.session import ProfileSession

PASSWORD = "a correct long passphrase"


def _profile(tmp_path):
    session = ProfileSession(tmp_path / "Documents" / "Lightning")
    session.prepare("Home", PASSWORD, PASSWORD, "What was the name of your first school?", "El Orman")
    session.confirm(session.pending.recovery)
    path, folder = session.paths.db_path, session.paths.backups_dir
    session.close()
    session.folder = folder
    return session, path


def _backups(session, path):
    return [entry for entry in list_backups(session.folder, path) if not entry.pre_upgrade]


def test_one_start_backup_a_day(tmp_path, monkeypatch):
    session, path = _profile(tmp_path)
    monkeypatch.setattr(backup_module, "_today", lambda: "2026-10-21")
    for _ in range(2):
        session.unlock(str(path), PASSWORD)
        session.close()
    assert [entry.date for entry in _backups(session, path)] == ["2026-10-21"]

    monkeypatch.setattr(backup_module, "_today", lambda: "2026-10-22")
    session.unlock(str(path), PASSWORD)
    session.close()
    assert [entry.date for entry in _backups(session, path)] == ["2026-10-22", "2026-10-21"]


def test_a_manual_backup_still_happens_and_counts_for_the_day(tmp_path, monkeypatch):
    session, path = _profile(tmp_path)
    monkeypatch.setattr(backup_module, "_today", lambda: "2026-10-21")
    session.unlock(str(path), PASSWORD)
    assert session.container.backup_now() is not None
    session.close()
    session.unlock(str(path), PASSWORD)
    session.close()
    assert len(_backups(session, path)) == 2  # the start backup and the manual one; no second start backup


def test_unlock_checks_the_source_once_and_the_copy_once(tmp_path, monkeypatch):
    session, path = _profile(tmp_path)
    copies = []
    real = snapshot_module.verify_connection
    monkeypatch.setattr(snapshot_module, "verify_connection",
                        lambda conn, **kwargs: copies.append(1) or real(conn, **kwargs))
    session.unlock(str(path), PASSWORD)
    session.close()
    assert len(_backups(session, path)) == 1
    assert len(copies) == 1  # the copy; the source was checked by the unlock itself just before
