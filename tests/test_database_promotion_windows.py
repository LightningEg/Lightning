from __future__ import annotations

import os
from dataclasses import replace

import pytest

from lightning.database.promotion_windows import WindowsPromotionFileOps


def test_windows_adapter_import_and_name_validation_are_portable():
    assert WindowsPromotionFileOps.validate_name("profile_01.db") == "profile_01.db"
    for name in ("../outside.db", "subdir\\outside.db", "C:stream", "bad?.db", "NUL.txt", "trailing."):
        with pytest.raises(ValueError):
            WindowsPromotionFileOps.validate_name(name)
    if os.name != "nt":
        with pytest.raises(OSError, match="only on Windows"):
            WindowsPromotionFileOps(".")


windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows file-operation adapter tests")


def put(path, value):
    path.write_bytes(value)


@windows_only
def test_copy_exclusive_flushes_and_verifies_bytes(tmp_path):
    put(tmp_path / "live.db", b"old database bytes")
    with WindowsPromotionFileOps(tmp_path) as adapter:
        adapter.copy_exclusive("live.db", "previous.db")
        assert adapter.sha256("previous.db") == adapter.sha256("live.db")
        with pytest.raises(OSError):
            adapter.copy_exclusive("live.db", "previous.db")
    assert (tmp_path / "previous.db").read_bytes() == b"old database bytes"


@windows_only
def test_replace_uses_same_directory_and_retains_previous_checkpoint(tmp_path):
    put(tmp_path / "live.db", b"old")
    put(tmp_path / "candidate.db", b"new")
    with WindowsPromotionFileOps(tmp_path) as adapter:
        adapter.copy_exclusive("live.db", "previous.db")
        expected_hash = adapter.sha256("candidate.db")
        adapter.atomic_replace("candidate.db", "live.db")
        assert adapter.sha256("live.db") == expected_hash
        assert (tmp_path / "live.db").read_bytes() == b"new"
        assert (tmp_path / "previous.db").read_bytes() == b"old"
        assert not (tmp_path / "candidate.db").exists()


@windows_only
def test_copy_flush_failure_keeps_source_and_removes_partial(tmp_path, monkeypatch):
    put(tmp_path / "live.db", b"old")
    with WindowsPromotionFileOps(tmp_path) as adapter:
        def fail_flush(handle):
            raise OSError("injected FlushFileBuffers failure")

        monkeypatch.setattr(adapter, "_flush_file", fail_flush)
        with pytest.raises(OSError, match="FlushFileBuffers"):
            adapter.copy_exclusive("live.db", "previous.db")
        assert (tmp_path / "live.db").read_bytes() == b"old"
        assert not (tmp_path / "previous.db").exists()
        assert list(tmp_path.glob(".lp-*.partial")) == []


@windows_only
def test_move_failure_preserves_live_candidate_and_previous(tmp_path, monkeypatch):
    put(tmp_path / "live.db", b"old")
    put(tmp_path / "candidate.db", b"new")
    put(tmp_path / "previous.db", b"old")
    with WindowsPromotionFileOps(tmp_path) as adapter:
        def fail_move(source, destination, flags):
            raise OSError("injected MoveFileExW failure")

        monkeypatch.setattr(adapter, "_move_file", fail_move)
        with pytest.raises(OSError, match="MoveFileExW"):
            adapter.atomic_replace("candidate.db", "live.db")
    assert (tmp_path / "live.db").read_bytes() == b"old"
    assert (tmp_path / "candidate.db").read_bytes() == b"new"
    assert (tmp_path / "previous.db").read_bytes() == b"old"


@windows_only
def test_post_replace_flush_failure_keeps_previous_for_blocked_recovery(tmp_path, monkeypatch):
    put(tmp_path / "live.db", b"old")
    put(tmp_path / "candidate.db", b"new")
    put(tmp_path / "previous.db", b"old")
    with WindowsPromotionFileOps(tmp_path) as adapter:
        original_flush = adapter._flush_file
        calls = 0

        def fail_second_flush(handle):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected published-file flush failure")
            original_flush(handle)

        monkeypatch.setattr(adapter, "_flush_file", fail_second_flush)
        with pytest.raises(OSError, match="published-file flush"):
            adapter.atomic_replace("candidate.db", "live.db")
    # Namespace replacement happened; caller must leave authority blocked and
    # recover from hashes. This adapter does not claim POSIX directory fsync.
    assert (tmp_path / "live.db").read_bytes() == b"new"
    assert (tmp_path / "previous.db").read_bytes() == b"old"


@windows_only
def test_hardlinks_and_reparse_points_are_rejected(tmp_path):
    put(tmp_path / "live.db", b"old")
    os.link(tmp_path / "live.db", tmp_path / "hard.db")
    with WindowsPromotionFileOps(tmp_path) as adapter:
        with pytest.raises(ValueError, match="Hard-linked"):
            adapter.sha256("hard.db")
        try:
            (tmp_path / "link.db").symlink_to(tmp_path / "live.db")
        except (OSError, NotImplementedError):
            pytest.skip("Windows symlink creation is unavailable in this environment")
        with pytest.raises(ValueError, match="Reparse-point"):
            adapter.sha256("link.db")


@windows_only
def test_reparse_root_is_rejected(tmp_path):
    root = tmp_path / "real-root"
    root.mkdir()
    alias = tmp_path / "root-alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Windows symlink creation is unavailable in this environment")
    with pytest.raises(ValueError, match="reparse points"):
        WindowsPromotionFileOps(alias)


@windows_only
def test_restore_manifest_create_and_update_use_write_through_moves(tmp_path, monkeypatch):
    from lightning.database.promotion_windows import MOVEFILE_WRITE_THROUGH
    from lightning.runtime.restore import EncryptedBackupRestorer, RestoreManifest

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
    moves = []
    original_move = WindowsPromotionFileOps._move_file

    def record_move(self, source, destination, flags):
        moves.append(flags)
        return original_move(self, source, destination, flags)

    monkeypatch.setattr(WindowsPromotionFileOps, "_move_file", record_move)
    path = tmp_path / f".lightning-restore-{'1' * 32}.state"
    EncryptedBackupRestorer._write_restore_manifest(path, manifest)
    EncryptedBackupRestorer._write_restore_manifest(
        path, replace(manifest, state="COMPLETE"), replace_existing=True,
    )
    assert RestoreManifest.from_bytes(path.read_bytes()).state == "COMPLETE"
    assert len(moves) >= 2
    assert all(flags & MOVEFILE_WRITE_THROUGH for flags in moves)


@windows_only
@pytest.mark.parametrize("replace_existing", [False, True])
def test_restore_manifest_publication_failure_preserves_authoritative_marker(
    tmp_path, monkeypatch, replace_existing,
):
    from dataclasses import replace
    from lightning.runtime.restore import EncryptedBackupRestorer, RestoreManifest

    manifest = RestoreManifest(
        state="PENDING", operation_id="1" * 32, profile_id="profile-1",
        live_name="profile.db", old_checkpoint_id="restore-base-" + "a" * 32,
        old_sha256="a" * 64, candidate_name="candidate.partial",
        new_checkpoint_id="restore-" + "2" * 32, candidate_sha256="b" * 64,
        previous_name=f".lightning-restore-{'1' * 32}.previous.db",
        source_backup_name="profile_backup_2030-01-01_001_1234abcd.db",
        source_sha256="c" * 64,
        source_copy_name=f".lightning-restore-source-{'1' * 32}.db",
        source_copy_sha256="c" * 64,
        pre_restore_name="profile_upgrade_2030-01-01_001_1234abcd.db",
        pre_restore_sha256="d" * 64,
    )
    marker = tmp_path / f".lightning-restore-{'1' * 32}.state"
    if replace_existing:
        EncryptedBackupRestorer._write_restore_manifest(marker, manifest)
    old_bytes = marker.read_bytes() if replace_existing else None

    def fail_publication(*args, **kwargs):
        raise OSError("injected marker publication failure")

    method = "atomic_replace" if replace_existing else "copy_exclusive"
    monkeypatch.setattr(WindowsPromotionFileOps, method, fail_publication)
    candidate = replace(manifest, state="COMPLETE") if replace_existing else manifest
    with pytest.raises(OSError, match="marker publication"):
        EncryptedBackupRestorer._write_restore_manifest(
            marker, candidate, replace_existing=replace_existing,
        )

    if replace_existing:
        assert marker.read_bytes() == old_bytes
    else:
        assert not marker.exists()
    assert list(tmp_path.glob(f".{marker.name}-*.partial")) == []
