"""Encrypted backup restore preparation and durable promotion."""
from __future__ import annotations

import hashlib
import json
import errno
import os
import re
import secrets
import sqlite3
import shutil
import stat
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from pathlib import PurePath
from uuid import uuid4

from lightning.database.backup import backup, list_backups
from lightning.database.connection import Database
from lightning.database.migrator import inspect_schema, migrate
from lightning.database.promotion import (
    CandidatePromotionService, PromotionBlocked, PromotionControlState, PromotionPhase,
    SqlitePromotionJournalStore,
)
from lightning.database.seed import seed
from lightning.database.snapshot import verify_connection
from lightning.database.staging import stage_database
from lightning.ownership_migration import migrate_legacy_ownership
from lightning.runtime.paths import ProfilePaths
from lightning.security.keys import unwrap_key
from .session import ProfileError, read_slot


_MANIFEST_FIELDS = {
    "schema_version", "state", "operation_id", "profile_id", "live_name",
    "old_checkpoint_id", "old_sha256", "candidate_name", "new_checkpoint_id",
    "candidate_sha256", "previous_name", "source_backup_name", "source_sha256",
    "source_copy_name", "source_copy_sha256", "pre_restore_name", "pre_restore_sha256",
}
_MAX_MANIFEST_BYTES = 16 * 1024


def _manifest_hash(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64 and
            all(char in "0123456789abcdef" for char in value))


def _manifest_name(value: object) -> bool:
    return (isinstance(value, str) and bool(value) and len(value) <= 255 and
            PurePath(value).name == value and value not in {".", ".."} and
            "/" not in value and "\\" not in value and "\x00" not in value)


@dataclass(frozen=True)
class RestoreManifest:
    """Durable P0 evidence that binds restore intent to every retained copy."""

    state: str
    operation_id: str
    profile_id: str
    live_name: str
    old_checkpoint_id: str
    old_sha256: str
    candidate_name: str
    new_checkpoint_id: str
    candidate_sha256: str
    previous_name: str
    source_backup_name: str
    source_sha256: str
    source_copy_name: str
    source_copy_sha256: str
    pre_restore_name: str
    pre_restore_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.state not in {"PENDING", "COMPLETE", "ABANDONED"}:
            raise ValueError("Unsupported restore manifest version or state")
        if not re.fullmatch(r"[0-9a-f]{32}", self.operation_id):
            raise ValueError("Invalid restore operation ID")
        if not isinstance(self.profile_id, str) or not self.profile_id or len(self.profile_id) > 200:
            raise ValueError("Invalid restore profile ID")
        if not isinstance(self.old_checkpoint_id, str) or not self.old_checkpoint_id:
            raise ValueError("Invalid old checkpoint ID")
        if not isinstance(self.new_checkpoint_id, str) or not self.new_checkpoint_id:
            raise ValueError("Invalid new checkpoint ID")
        if (self.old_checkpoint_id != "restore-base-" + self.old_sha256[:32] or
                self.new_checkpoint_id == self.old_checkpoint_id):
            raise ValueError("Restore checkpoint IDs do not bind to their operation")
        if not re.fullmatch(r"restore-[0-9a-f]{32}", self.new_checkpoint_id):
            raise ValueError("Invalid new restore checkpoint ID")
        for name in (self.live_name, self.candidate_name, self.previous_name,
                     self.source_backup_name, self.source_copy_name, self.pre_restore_name):
            if not _manifest_name(name):
                raise ValueError("Restore manifest names must be sibling basenames")
        for digest in (self.old_sha256, self.candidate_sha256, self.source_sha256,
                       self.source_copy_sha256, self.pre_restore_sha256):
            if not _manifest_hash(digest):
                raise ValueError("Restore manifest hashes must be lowercase SHA-256")
        if self.source_sha256 != self.source_copy_sha256:
            raise ValueError("Protected source copy hash differs from selected backup")
        if self.source_copy_name != f".lightning-restore-source-{self.operation_id}.db":
            raise ValueError("Protected source copy path does not match operation ID")
        if self.previous_name != f".lightning-restore-{self.operation_id}.previous.db":
            raise ValueError("Previous checkpoint path does not match operation ID")

    def to_bytes(self) -> bytes:
        record = {field: getattr(self, field) for field in _MANIFEST_FIELDS}
        return (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

    @classmethod
    def from_bytes(cls, raw: bytes) -> RestoreManifest:
        if not isinstance(raw, bytes) or len(raw) > _MAX_MANIFEST_BYTES:
            raise ValueError("Restore manifest is too large or not bytes")
        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate restore manifest field")
                result[key] = value
            return result

        record = json.loads(raw, object_pairs_hook=no_duplicates)
        if not isinstance(record, dict) or set(record) != _MANIFEST_FIELDS:
            raise ValueError("Restore manifest fields do not match schema")
        if type(record["schema_version"]) is not int:
            raise ValueError("Restore manifest version must be an integer")
        for name in _MANIFEST_FIELDS - {"schema_version"}:
            if not isinstance(record[name], str):
                raise ValueError("Restore manifest values must be text")
        return cls(**record)


@contextmanager
def _held_profile_lock(lock):
    """Expose the already-acquired process gate to the promotion service."""
    if not lock.acquired:
        raise RuntimeError("Profile instance lock is not held")
    yield


class EncryptedBackupRestorer:
    """Keep restore I/O out of the live session lifecycle controller."""

    def __init__(self, session):
        self.session = session

    @staticmethod
    def _sidecars(path: Path) -> tuple[Path, ...]:
        return tuple(Path(str(path) + suffix) for suffix in ("-wal", "-journal", "-shm"))

    @classmethod
    def _require_clean_database_file(cls, path: Path) -> None:
        if path.is_symlink():
            raise ProfileError("Restore is blocked because a database path is a symbolic link.")
        try:
            info = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise ProfileError("Restore is blocked because a database file cannot be inspected.") from exc
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProfileError("Restore is blocked because a database file is not a private regular file.")
        if any(sidecar.exists() or sidecar.is_symlink() for sidecar in cls._sidecars(path)):
            raise ProfileError("Restore is blocked while SQLite journal or WAL sidecars exist. Close Lightning and retry after the database is cleanly checkpointed.")

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @classmethod
    def _verify_file(cls, path: Path, key: bytes) -> None:
        cls._require_clean_database_file(path)
        db = Database(path, key=key, read_only=True)
        try:
            if not db.has_table("schema_migrations"):
                raise ProfileError("The selected file is not a Lightning database.")
            inspect_schema(db)
            verify_connection(db.conn, encrypted=True)
        finally:
            db.close()
        cls._require_clean_database_file(path)

    @staticmethod
    def _restore_journal_paths(paths: ProfilePaths) -> tuple[Path, ...]:
        return tuple(paths.data_dir.glob(".lightning-restore-*.sqlite"))

    @staticmethod
    def _restore_marker_paths(paths: ProfilePaths) -> tuple[Path, ...]:
        return tuple(paths.data_dir.glob(".lightning-restore-*.state"))

    @staticmethod
    def _matches_unprepared_restore(state: PromotionControlState, manifest: RestoreManifest) -> bool:
        return state.journal is None and (
            state.accepted is None or (
                state.accepted.checkpoint_id == manifest.old_checkpoint_id and
                state.accepted.sha256 == manifest.old_sha256
            )
        )

    @staticmethod
    def _write_restore_manifest(path: Path, manifest: RestoreManifest, *, replace_existing: bool = False) -> None:
        temporary = path.with_name(f".{path.name}-{secrets.token_hex(12)}.partial")
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(manifest.to_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            if os.name == "nt":
                from lightning.database.promotion_windows import WindowsPromotionFileOps
                with WindowsPromotionFileOps(path.parent) as adapter:
                    existing = adapter.sha256(path.name)
                    if existing is None and not replace_existing:
                        adapter.copy_exclusive(temporary.name, path.name)
                        adapter.unlink(temporary.name)
                    elif existing is not None and replace_existing:
                        adapter.atomic_replace(temporary.name, path.name)
                    else:
                        raise FileExistsError(path) if existing is not None else FileNotFoundError(path)
            else:
                exists = path.exists() or path.is_symlink()
                if exists and replace_existing:
                    if path.is_symlink():
                        raise OSError("Restore manifest path must not be a symlink")
                    os.replace(temporary, path)
                elif not exists and not replace_existing:
                    try:
                        os.link(temporary, path)
                    except OSError as exc:
                        # Some Android/private-storage filesystems refuse hard
                        # links. The profile directory is private and held by
                        # the profile lock, so a same-directory rename keeps
                        # publication atomic there without exposing partial JSON.
                        unsupported = {errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.EXDEV}
                        if exc.errno not in unsupported or path.exists() or path.is_symlink():
                            raise
                        os.rename(temporary, path)
                    else:
                        temporary.unlink()
                else:
                    raise FileExistsError(path) if exists else FileNotFoundError(path)
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _preserve_source_backup(source: Path, folder: Path, operation_id: str) -> Path:
        target = folder / f".lightning-restore-source-{operation_id}.db"
        source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        target_fd = None
        try:
            target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(source_fd, "rb", closefd=False) as input_file, os.fdopen(
                target_fd, "wb", closefd=False
            ) as output_file:
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                output_file.flush()
                os.fsync(output_file.fileno())
            if os.name != "nt":
                directory_fd = os.open(folder, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            os.close(source_fd)
            if target_fd is not None:
                os.close(target_fd)
        return target

    @classmethod
    def _check_restore_control(cls, paths: ProfilePaths, key: bytes | None = None) -> None:
        # Sync authority is deliberately not inferred from a missing store.
        # These reserved paths are the integration boundary for the future sync
        # control store; until its API exists, any such state blocks local restore.
        reserved = (paths.data_dir / ".sync", paths.data_dir / "sync-control.sqlite",
                    paths.data_dir / ".lightning-sync.sqlite")
        if any(path.exists() or path.is_symlink() for path in reserved):
            raise ProfileError("Restore is unavailable while sync authority state exists or cannot be verified.")
        manifests: dict[str, RestoreManifest] = {}
        abandoned: set[str] = set()
        for marker in cls._restore_marker_paths(paths):
            try:
                info = marker.stat(follow_symlinks=False)
                if marker.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise OSError("unsafe restore manifest")
                with marker.open("rb") as handle:
                    manifest = RestoreManifest.from_bytes(handle.read(_MAX_MANIFEST_BYTES + 1))
            except OSError as exc:
                raise ProfileError("Restore operation manifest cannot be read; this profile is locked for repair.") from exc
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ProfileError("Restore operation manifest is malformed; this profile is locked for repair.") from exc
            operation_id = marker.name.removeprefix(".lightning-restore-").removesuffix(".state")
            if (manifest.operation_id != operation_id or paths.profile is None or
                    manifest.profile_id != paths.profile.profile_id or
                    manifest.live_name != paths.db_path.name):
                raise ProfileError("Restore operation manifest belongs to another operation or profile.")
            if manifest.state == "ABANDONED":
                try:
                    # Retirement already proved that live was unchanged. Its
                    # durable receipt must allow later ordinary edits and
                    # restores, while retained recovery evidence stays checked.
                    for name, expected in ((manifest.source_copy_name, manifest.source_copy_sha256),
                                           (manifest.pre_restore_name, manifest.pre_restore_sha256)):
                        evidence = paths.backups_dir / name
                        cls._require_clean_database_file(evidence)
                        if cls._digest(evidence) != expected:
                            raise ProfileError("Abandoned restore evidence does not match its manifest.")
                        if key is not None:
                            cls._verify_file(evidence, key)
                except Exception as exc:
                    raise ProfileError("Abandoned restore evidence is missing, unsafe, or corrupt.") from exc
                manifests[marker.name.removesuffix(".state")] = manifest
                abandoned.add(marker.name.removesuffix(".state"))
                continue
            if manifest.state != "COMPLETE":
                raise ProfileError("An interrupted restore needs repair before this profile can be unlocked.")
            manifests[marker.name.removesuffix(".state")] = manifest
        journals: dict[str, object] = {}
        for control in cls._restore_journal_paths(paths):
            marker_id = control.name.removesuffix(".sqlite")
            manifest = manifests.get(marker_id)
            if manifest is None:
                raise ProfileError("A restore journal has no matching operation manifest; this profile is locked for repair.")
            try:
                info = control.stat(follow_symlinks=False)
                if control.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise OSError("unsafe restore journal")
                connection = sqlite3.connect(control.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
                try:
                    row = connection.execute(
                        "SELECT accepted_checkpoint_id, accepted_sha256, journal_json "
                        "FROM promotion_control WHERE singleton=1"
                    ).fetchone()
                    state = SqlitePromotionJournalStore._row_state(row)
                finally:
                    connection.close()
            except Exception as exc:
                raise ProfileError("Restore control state is damaged. This profile is locked for repair.") from exc
            if marker_id in abandoned:
                if not cls._matches_unprepared_restore(state, manifest):
                    raise ProfileError("An abandoned restore has conflicting control state and needs repair before unlock.")
                continue
            journal = state.journal
            if (journal is None or state.accepted is None or
                    journal.phase is not PromotionPhase.ACTIVATED or
                    journal.operation_id != manifest.operation_id or
                    state.accepted.checkpoint_id != journal.new_checkpoint_id or
                    state.accepted.sha256 != journal.new_sha256 or
                    journal.live_name != manifest.live_name or
                    journal.candidate_name != manifest.candidate_name or
                    journal.previous_name != manifest.previous_name or
                    journal.old_checkpoint_id != manifest.old_checkpoint_id or
                    journal.old_sha256 != manifest.old_sha256 or
                    journal.new_checkpoint_id != manifest.new_checkpoint_id or
                    journal.new_sha256 != manifest.candidate_sha256):
                raise ProfileError("An interrupted restore needs repair before this profile can be unlocked.")
            source_copy = paths.backups_dir / manifest.source_copy_name
            pre_restore = paths.backups_dir / manifest.pre_restore_name
            original_source = paths.backups_dir / manifest.source_backup_name
            try:
                cls._require_clean_database_file(source_copy)
                cls._require_clean_database_file(pre_restore)
                if (cls._digest(source_copy) != manifest.source_copy_sha256 or
                        cls._digest(pre_restore) != manifest.pre_restore_sha256):
                    raise ProfileError("A retained restore backup does not match its manifest.")
                if original_source.exists():
                    cls._require_clean_database_file(original_source)
                    if cls._digest(original_source) != manifest.source_sha256:
                        raise ProfileError("The selected source backup no longer matches its manifest.")
                if key is not None:
                    cls._verify_file(source_copy, key)
                    cls._verify_file(pre_restore, key)
            except Exception as exc:
                raise ProfileError("A retained restore backup is missing, unsafe, or corrupt.") from exc
            previous = paths.data_dir / journal.previous_name
            try:
                cls._require_clean_database_file(previous)
                previous_hash = cls._digest(previous)
            except ProfileError as exc:
                raise ProfileError("The retained pre-restore checkpoint is missing or unsafe.") from exc
            if previous_hash != journal.old_sha256:
                raise ProfileError("The retained pre-restore checkpoint is missing or does not match its journal.")
            if key is not None:
                try:
                    cls._verify_file(previous, key)
                except Exception as exc:
                    raise ProfileError("The retained pre-restore checkpoint cannot be verified.") from exc
            journals[marker_id] = journal
        if set(journals) != (set(manifests) - abandoned):
            raise ProfileError("A restore operation manifest has no complete matching journal; this profile is locked for repair.")
        expected_source_copies = {manifest.source_copy_name for manifest in manifests.values()}
        actual_source_copies = {path.name for path in paths.backups_dir.glob(".lightning-restore-source-*.db")}
        if actual_source_copies != expected_source_copies:
            raise ProfileError("A protected source copy is missing or has no matching restore manifest.")
        for previous in paths.data_dir.glob(".lightning-restore-*.previous.db"):
            operation_marker = previous.name.removesuffix(".previous.db") + ".state"
            if operation_marker not in {path.name for path in cls._restore_marker_paths(paths)}:
                raise ProfileError("A retained restore checkpoint has no safely completed operation record; this profile is locked for repair.")

    def restore_backup(self, selected: str, backup_path: str, password: str) -> None:
        """Restore one verified encrypted backup into its existing standalone profile.

        The backup and current live database are retained. All staging and
        migration happens on a private candidate before the P0–P5 publication.
        """
        self.session._attempt()
        self.session._locked()
        paths = self.session._select(selected)
        if paths.profile is None:
            raise ProfileError("Restore requires a named Lightning profile.")
        lock = self.session._acquire(paths)
        staged = None
        try:
            try:
                key = unwrap_key(read_slot(paths.keys_path), password)
            except (ProfileError, ValueError) as exc:
                raise ProfileError("The profile password could not unlock its encrypted database.") from exc
            self._check_restore_control(paths, key)
            self._require_clean_database_file(paths.db_path)
            entries = list_backups(paths.backups_dir, paths.db_path)
            selected_backup = Path(backup_path)
            try:
                selected_resolved = selected_backup.resolve(strict=True)
            except OSError as exc:
                raise ProfileError("Choose a completed backup from this profile.") from exc
            entry = next((item for item in entries if item.path.resolve() == selected_resolved), None)
            if entry is None:
                raise ProfileError("Choose a completed backup from this profile.")
            source = entry.path
            self._require_clean_database_file(source)
            source_hash = self._digest(source)
            operation_id = uuid4().hex
            possible_collision = (
                paths.data_dir / f".lightning-restore-{operation_id}.sqlite",
                paths.data_dir / f".lightning-restore-{operation_id}.state",
                paths.data_dir / f".lightning-restore-{operation_id}.previous.db",
                paths.backups_dir / f".lightning-restore-source-{operation_id}.db",
            )
            if any(path.exists() or path.is_symlink() for path in possible_collision):
                raise ProfileError("Restore operation ID collision; no files were replaced.")
            try:
                self._verify_file(source, key)
            except Exception as exc:
                raise ProfileError("The selected backup is damaged, uses another key, or needs a newer Lightning version.") from exc
            if self._digest(source) != source_hash:
                raise ProfileError("The selected backup changed during verification.")

            # Preserve the current live contents, including any committed WAL
            # snapshot semantics. keep=0 is intentional: no retention pruning.
            current = Database(paths.db_path, key=key, read_only=True)
            try:
                saved = backup(current, paths.backups_dir, keep=0, pre_upgrade=True)
            finally:
                current.close()
            if saved is None:
                raise ProfileError("Could not create a verified pre-restore backup; restore was cancelled.")
            saved_hash = self._digest(saved)
            self._verify_file(saved, key)

            staged = stage_database(source, paths.data_dir, destination_key=key, source_key=key)
            candidate = staged.path
            self._migrate_candidate(candidate, key)
            self._verify_file(candidate, key)
            self._require_clean_database_file(paths.db_path)
            if self._digest(source) != source_hash:
                raise ProfileError("The selected backup changed during staging; restore was cancelled.")
            # Open the file adapter before recording intent: a folder it refuses
            # (a reparse point such as OneDrive on Windows) must cancel the
            # restore cleanly, not leave a pending record that locks the profile.
            try:
                if os.name == "nt":
                    from lightning.database.promotion_windows import WindowsPromotionFileOps
                    file_ops = WindowsPromotionFileOps(paths.data_dir)
                else:
                    from lightning.database.promotion import PosixPromotionFileOps
                    file_ops = PosixPromotionFileOps(paths.data_dir)
            except (OSError, ValueError) as exc:
                raise ProfileError("Restore cannot run in this profile's folder (it may be a synced or linked folder). Nothing was replaced.") from exc
            # Until the PENDING manifest exists, nothing refers to the protected
            # source copy; remove it on failure so it cannot lock the profile.
            preserved_source = None
            marker_path = paths.data_dir / f".lightning-restore-{operation_id}.state"
            manifest_written = False
            try:
                preserved_source = self._preserve_source_backup(source, paths.backups_dir, operation_id)
                if self._digest(preserved_source) != source_hash:
                    raise ProfileError("Could not preserve the selected backup bytes; restore was cancelled.")

                live_hash = self._digest(paths.db_path)
                store_path = paths.data_dir / f".lightning-restore-{operation_id}.sqlite"
                old_checkpoint = "restore-base-" + live_hash[:32]
                self._require_clean_database_file(paths.db_path)
                self._require_clean_database_file(candidate)
                previous_name = f".lightning-restore-{operation_id}.previous.db"
                new_checkpoint = "restore-" + uuid4().hex
                manifest = RestoreManifest(
                    state="PENDING",
                    operation_id=operation_id,
                    profile_id=paths.profile.profile_id,
                    live_name=paths.db_path.name,
                    old_checkpoint_id=old_checkpoint,
                    old_sha256=live_hash,
                    candidate_name=candidate.name,
                    new_checkpoint_id=new_checkpoint,
                    candidate_sha256=self._digest(candidate),
                    previous_name=previous_name,
                    source_backup_name=source.name,
                    source_sha256=source_hash,
                    source_copy_name=preserved_source.name,
                    source_copy_sha256=self._digest(preserved_source),
                    pre_restore_name=saved.name,
                    pre_restore_sha256=saved_hash,
                )
                if store_path.exists() or marker_path.exists() or marker_path.is_symlink():
                    raise ProfileError("Restore operation ID collision; no files were replaced.")
                self._write_restore_manifest(marker_path, manifest)
                manifest_written = True
            except BaseException:
                if (not manifest_written and preserved_source is not None
                        and not (marker_path.exists() or marker_path.is_symlink())):
                    preserved_source.unlink(missing_ok=True)
                file_ops.close()
                raise
            try:
                store = SqlitePromotionJournalStore(store_path)
                state = store.read_state()
                if state.accepted is not None or state.journal is not None:
                    raise ProfileError("Restore control state is not empty; this profile is locked for repair.")
                store.initialize_accepted(old_checkpoint, live_hash)
            except BaseException:
                file_ops.close()
                raise
            try:
                service = CandidatePromotionService(file_ops, store)
                def verify(name: str) -> None:
                    self._verify_file(paths.data_dir / name, key)

                def mark_ready(_checkpoint: str, live_name: str) -> None:
                    # P4 is durable; P5 records readiness while the UI remains
                    # locked. The ordinary writable builder runs on a later unlock.
                    self._verify_file(paths.data_dir / live_name, key)

                result = service.promote(
                    operation_id=operation_id,
                    old_checkpoint_id=old_checkpoint,
                    new_checkpoint_id=new_checkpoint,
                    live_name=paths.db_path.name,
                    candidate_name=candidate.name,
                    previous_name=previous_name,
                    operation_gate=_held_profile_lock(lock),
                    verify_database=verify,
                    activate=mark_ready,
                )
                if result.phase is not PromotionPhase.ACTIVATED:
                    raise ProfileError("Restore did not reach durable activation; this profile remains locked.")
                if self._digest(source) != source_hash:
                    raise ProfileError("The selected backup changed during publication; this profile remains locked for repair.")
                self._write_restore_manifest(marker_path, replace(manifest, state="COMPLETE"),
                                             replace_existing=True)
                self.session.retry_at = 0.0
            finally:
                file_ops.close()
        except Exception as exc:
            if isinstance(exc, ProfileError):
                raise
            if isinstance(exc, PromotionBlocked):
                raise ProfileError("Restore needs repair. The profile remains locked and recovery files were preserved.") from exc
            raise ProfileError("Restore failed safely. The profile remains locked and recovery files were preserved.") from exc
        finally:
            if staged is not None:
                # Keep failed candidates as evidence; remove only a successful
                # unreferenced partial after it has been atomically consumed.
                if not staged.path.exists():
                    staged.path.unlink(missing_ok=True)
            lock.close()

    def resume_interrupted_restore(self, selected: str, password: str) -> None:
        """Resume a pending restore, or retire its verified untouched intent.

        A prepared promotion only moves forward; there is no rollback path.
        Uncertainty in the manifest, control state, retained source or snapshot
        leaves the profile locked with its recovery evidence intact.
        """
        self.session._attempt()
        self.session._locked()
        paths = self.session._select(selected)
        if paths.profile is None:
            raise ProfileError("Restore recovery requires a named Lightning profile.")
        lock = self.session._acquire(paths)
        file_ops = None
        try:
            try:
                key = unwrap_key(read_slot(paths.keys_path), password)
            except (ProfileError, ValueError) as exc:
                raise ProfileError("The profile password could not unlock its encrypted database.") from exc
            reserved = (paths.data_dir / ".sync", paths.data_dir / "sync-control.sqlite",
                        paths.data_dir / ".lightning-sync.sqlite")
            if any(path.exists() or path.is_symlink() for path in reserved):
                raise ProfileError("Restore recovery is unavailable while sync authority state exists or cannot be verified.")

            markers = self._restore_marker_paths(paths)
            pending: list[tuple[Path, RestoreManifest]] = []
            for marker in markers:
                try:
                    info = marker.stat(follow_symlinks=False)
                    if marker.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise OSError("unsafe restore manifest")
                    with marker.open("rb") as handle:
                        manifest = RestoreManifest.from_bytes(handle.read(_MAX_MANIFEST_BYTES + 1))
                except Exception as exc:
                    raise ProfileError("A restore operation manifest is malformed or unsafe; this profile remains locked.") from exc
                marker_id = marker.name.removeprefix(".lightning-restore-").removesuffix(".state")
                if (marker_id != manifest.operation_id or paths.profile.profile_id != manifest.profile_id or
                        paths.db_path.name != manifest.live_name):
                    raise ProfileError("A restore manifest belongs to another operation or profile.")
                if manifest.state == "PENDING":
                    pending.append((marker, manifest))
            if len(pending) != 1:
                raise ProfileError("Resume requires exactly one pending restore operation.")
            marker, manifest = pending[0]
            manifest_ids = {path.name.removeprefix(".lightning-restore-").removesuffix(".state")
                            for path in markers}
            for control in self._restore_journal_paths(paths):
                control_id = control.name.removeprefix(".lightning-restore-").removesuffix(".sqlite")
                if control_id not in manifest_ids:
                    raise ProfileError("An unclaimed restore journal blocks recovery; this profile remains locked.")
            journal_path = paths.data_dir / f".lightning-restore-{manifest.operation_id}.sqlite"
            store = None
            observed = None
            if journal_path.exists() or journal_path.is_symlink():
                try:
                    info = journal_path.stat(follow_symlinks=False)
                    if journal_path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise OSError("unsafe restore journal")
                    # Read-write under the held profile lock: a crash inside a
                    # control transaction can leave a hot journal to roll back.
                    # Validate the existing record before using the store's
                    # constructor, which initializes a new schema/singleton.
                    # Missing control records must stay ambiguous, not become
                    # empty stores that appear safe to retire.
                    connection = sqlite3.connect(journal_path, timeout=5, isolation_level=None)
                    try:
                        connection.execute("PRAGMA synchronous=FULL")
                        observed = SqlitePromotionJournalStore._read_from(connection)
                    finally:
                        connection.close()
                    if observed.journal is not None:
                        store = SqlitePromotionJournalStore(journal_path)
                except Exception as exc:
                    raise ProfileError("The pending restore has no readable matching journal; this profile remains locked.") from exc
            if observed is None or observed.journal is None:
                if observed is not None and not self._matches_unprepared_restore(observed, manifest):
                    raise ProfileError("Pending restore manifest and unprepared control state disagree; this profile remains locked.")
                # PENDING precedes both control-store initialization and P1.
                # With no prepared journal and live still at the old hash, an
                # absent or empty matching control store can be safely retired.
                # Retire this abandoned intent so a crash in that narrow gap
                # does not permanently lock an otherwise untouched profile.
                try:
                    self._require_clean_database_file(paths.db_path)
                    if self._digest(paths.db_path) != manifest.old_sha256:
                        raise ProfileError("The live database changed after restore intent; this profile remains locked.")
                    for name, expected in ((manifest.source_copy_name, manifest.source_copy_sha256),
                                           (manifest.pre_restore_name, manifest.pre_restore_sha256)):
                        evidence = paths.backups_dir / name
                        self._require_clean_database_file(evidence)
                        if self._digest(evidence) != expected:
                            raise ProfileError("Protected restore evidence changed; this profile remains locked.")
                        self._verify_file(evidence, key)
                    self._write_restore_manifest(marker, replace(manifest, state="ABANDONED"),
                                                 replace_existing=True)
                    self.session.retry_at = 0.0
                    return
                except ProfileError:
                    raise
                except OSError as exc:
                    raise ProfileError("The abandoned restore intent could not be safely retired; this profile remains locked.") from exc
            journal = observed.journal
            if (journal is None or journal.operation_id != manifest.operation_id or
                    journal.phase not in (PromotionPhase.PREPARED, PromotionPhase.PREVIOUS_PROTECTED,
                                          PromotionPhase.FILE_PUBLISHED, PromotionPhase.AUTHORITY_PUBLISHED,
                                          PromotionPhase.ACTIVATED) or
                    journal.live_name != manifest.live_name or
                    journal.candidate_name != manifest.candidate_name or
                    journal.previous_name != manifest.previous_name or
                    journal.old_checkpoint_id != manifest.old_checkpoint_id or
                    journal.old_sha256 != manifest.old_sha256 or
                    journal.new_checkpoint_id != manifest.new_checkpoint_id or
                    journal.new_sha256 != manifest.candidate_sha256 or observed.accepted is None or
                    observed.accepted.checkpoint_id not in (manifest.old_checkpoint_id, manifest.new_checkpoint_id) or
                    observed.accepted.sha256 not in (manifest.old_sha256, manifest.candidate_sha256) or
                    (observed.accepted.checkpoint_id == manifest.old_checkpoint_id and
                     observed.accepted.sha256 != manifest.old_sha256) or
                    (observed.accepted.checkpoint_id == manifest.new_checkpoint_id and
                     observed.accepted.sha256 != manifest.candidate_sha256)):
                raise ProfileError("Pending restore manifest and journal disagree; this profile remains locked.")

            source_copy = paths.backups_dir / manifest.source_copy_name
            pre_restore = paths.backups_dir / manifest.pre_restore_name
            try:
                for path, expected in ((source_copy, manifest.source_copy_sha256),
                                       (pre_restore, manifest.pre_restore_sha256)):
                    self._require_clean_database_file(path)
                    if self._digest(path) != expected:
                        raise ProfileError("A protected restore file does not match its manifest.")
                    self._verify_file(path, key)
                original_source = paths.backups_dir / manifest.source_backup_name
                if original_source.exists() or original_source.is_symlink():
                    self._require_clean_database_file(original_source)
                    if self._digest(original_source) != manifest.source_sha256:
                        raise ProfileError("The selected backup no longer matches its manifest.")
            except Exception as exc:
                raise ProfileError("Protected restore source or pre-restore evidence is missing or corrupt; profile remains locked.") from exc

            if os.name == "nt":
                from lightning.database.promotion_windows import WindowsPromotionFileOps
                file_ops = WindowsPromotionFileOps(paths.data_dir)
            else:
                from lightning.database.promotion import PosixPromotionFileOps
                file_ops = PosixPromotionFileOps(paths.data_dir)
            service = CandidatePromotionService(file_ops, store)

            def verify(name: str) -> None:
                if not _manifest_name(name):
                    raise ProfileError("Promotion journal contains an unsafe file name.")
                self._verify_file(paths.data_dir / name, key)

            def remain_locked(_checkpoint: str, live_name: str) -> None:
                self._verify_file(paths.data_dir / live_name, key)

            try:
                result = service.recover(
                    live_name=manifest.live_name,
                    operation_gate=_held_profile_lock(lock),
                    verify_database=verify,
                    activate=remain_locked,
                )
                final = store.read_state()
                if (result.phase is not PromotionPhase.ACTIVATED or final.journal is None or
                        final.journal.operation_id != manifest.operation_id or
                        final.journal.phase is not PromotionPhase.ACTIVATED or final.accepted is None or
                        final.accepted.checkpoint_id != manifest.new_checkpoint_id or
                        final.accepted.sha256 != manifest.candidate_sha256):
                    raise ProfileError("Restore recovery did not reach the accepted P5 state; profile remains locked.")
                for path, expected in ((source_copy, manifest.source_copy_sha256),
                                       (pre_restore, manifest.pre_restore_sha256),
                                       (paths.data_dir / manifest.previous_name, manifest.old_sha256)):
                    self._require_clean_database_file(path)
                    if self._digest(path) != expected:
                        raise ProfileError("Restore recovery evidence changed; profile remains locked.")
                    self._verify_file(path, key)
                if (original_source.exists() or original_source.is_symlink()) and self._digest(original_source) != manifest.source_sha256:
                    raise ProfileError("The selected backup changed during restore recovery; profile remains locked.")
                self._write_restore_manifest(marker, replace(manifest, state="COMPLETE"),
                                             replace_existing=True)
                self.session.retry_at = 0.0
            finally:
                file_ops.close()
        except Exception as exc:
            if isinstance(exc, ProfileError):
                raise
            if isinstance(exc, PromotionBlocked):
                raise ProfileError("Restore recovery is blocked; the profile remains locked and evidence was preserved.") from exc
            raise ProfileError("Restore recovery failed safely; the profile remains locked and evidence was preserved.") from exc
        finally:
            lock.close()

    @staticmethod
    def _migrate_candidate(path: Path, key: bytes) -> None:
        """Apply supported migrations only to the private staged candidate."""
        db = Database(path, key=key)
        try:
            inspect_schema(db)
            migrate(db)
            seed(db)
            migrate_legacy_ownership(db)
        finally:
            db.close()
