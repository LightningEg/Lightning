"""One portable profile file (BT-2AI5): everything a fresh device needs to open a book.

A backup is the database alone, and the database is useless without the profile's key file. A profile file
is a ZIP (stored, never compressed) of three members: ``manifest.json``, ``keys.json`` (the key file as it
is: the password still guards it) and ``profile.db`` (a fresh verified encrypted snapshot, never the live
file). Reading one never touches an existing profile: it always publishes a new folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lightning.database.connection import Database
from lightning.database.migrator import inspect_schema
from lightning.database.snapshot import snapshot
from lightning.security.keys import unwrap_key, validate_key_file

from .paths import ProfilePaths, _sanitize_profile_name, create_profile, discover_profiles
from .session import ProfileError, publish_keys, publish_new, read_keys

FORMAT = "lightning-profile-v1"
SUFFIX = ".lightning"
MAX_BYTES = 256 * 1024 * 1024
_MANIFEST, _KEYS, _DATABASE = "manifest.json", "keys.json", "profile.db"
_MEMBERS = (_MANIFEST, _KEYS, _DATABASE)
_SMALL_MEMBER_BYTES = 16384  # the key file's own limit (session.read_slot); the manifest is far smaller
_BLOCK = 1024 * 1024

NOT_A_PROFILE_FILE = "This is not a Lightning profile file."
DAMAGED = "This profile file is damaged. Use another copy."
TOO_LARGE = "This profile file is too large to open."
WRONG_PASSWORD = "The password is incorrect."
UNREADABLE_DATABASE = "This profile file is damaged, or it was made by a newer Lightning. Update Lightning and try again."


@dataclass(frozen=True)
class OpenedProfile:
    """The new profile a profile file became. A journal profile arrives as a read-only review copy."""

    paths: ProfilePaths
    name: str
    review_copy: bool


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _fsync_directory(folder: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def profile_file_name(name: str, day: str | None = None) -> str:
    return f"{_sanitize_profile_name(name)}-{day or _today()}{SUFFIX}"


def write_profile_file(paths: ProfilePaths, key: bytes, out: str | Path, *, db: Database | None = None) -> Path:
    """Write ``<name>-<date>.lightning`` into the folder ``out`` and return it; an existing file is never replaced.

    ``db`` is the profile's open connection when the caller has one (the snapshot then runs on it, between
    saves); without it a read-only connection is opened for the snapshot. The caller holds the profile lock.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    name = paths.profile.name if paths.profile is not None else Path(paths.db_path).stem
    document = read_keys(paths)
    paths.backups_dir.mkdir(exist_ok=True)
    staged = paths.backups_dir / f".profile-file-{secrets.token_hex(12)}.partial"
    partial = out / f".profile-file-{secrets.token_hex(12)}.partial"
    own = db is None
    source = Database(paths.db_path, key=key, read_only=True) if own else db
    try:
        try:
            schema_version = inspect_schema(source).current_version
            snapshot(source, staged)
        finally:
            if own:
                source.close()
        if staged.stat().st_size > MAX_BYTES - 2 * _SMALL_MEMBER_BYTES:
            raise ProfileError("This profile is too large for one profile file.")
        keys = json.dumps(document, sort_keys=True).encode("utf-8")
        manifest = json.dumps({
            "format": FORMAT,
            "name": name,
            "schema_version": schema_version,
            "created": _today(),
            "sha256": {_KEYS: hashlib.sha256(keys).hexdigest(), _DATABASE: _sha256(staged)},
        }, sort_keys=True).encode("utf-8")
        descriptor = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                archive.writestr(zipfile.ZipInfo(_MANIFEST), manifest)
                archive.writestr(zipfile.ZipInfo(_KEYS), keys)
                with staged.open("rb") as reader, archive.open(zipfile.ZipInfo(_DATABASE), "w", force_zip64=True) as member:
                    shutil.copyfileobj(reader, member, _BLOCK)
            handle.flush()
            os.fsync(handle.fileno())
        stem = profile_file_name(name)[:-len(SUFFIX)]
        target, attempt = out / f"{stem}{SUFFIX}", 1
        while True:
            try:
                publish_new(partial, target)
                break
            except FileExistsError:
                attempt += 1
                target = out / f"{stem}-{attempt}{SUFFIX}"
        _fsync_directory(out)
        return target
    finally:
        staged.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)


def _checked_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    """Exactly the three members, each a plain stored file: no paths, links, folders, extras or duplicates."""
    entries = archive.infolist()
    if len(entries) != len(_MEMBERS) or {entry.filename for entry in entries} != set(_MEMBERS):
        raise ProfileError(NOT_A_PROFILE_FILE)
    for entry in entries:
        mode = entry.external_attr >> 16
        if (entry.is_dir() or entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits & 0x1
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
            raise ProfileError(NOT_A_PROFILE_FILE)
        limit = MAX_BYTES if entry.filename == _DATABASE else _SMALL_MEMBER_BYTES
        if entry.file_size > limit:
            raise ProfileError(TOO_LARGE if entry.filename == _DATABASE else NOT_A_PROFILE_FILE)
    return {entry.filename: entry for entry in entries}


def _small(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> bytes:
    with archive.open(entry) as handle:
        raw = handle.read(_SMALL_MEMBER_BYTES + 1)
    if len(raw) > _SMALL_MEMBER_BYTES:
        raise ProfileError(NOT_A_PROFILE_FILE)
    return raw


def _manifest(raw: bytes) -> dict:
    try:
        manifest = json.loads(raw)
    except ValueError as exc:
        raise ProfileError(NOT_A_PROFILE_FILE) from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ProfileError(NOT_A_PROFILE_FILE)
    name, hashes = manifest.get("name"), manifest.get("sha256")
    if (not isinstance(name, str) or not name.strip() or len(name) > 200
            or type(manifest.get("schema_version")) is not int
            or not isinstance(hashes, dict) or set(hashes) != {_KEYS, _DATABASE}
            or any(not isinstance(value, str) or len(value) != 64 for value in hashes.values())):
        raise ProfileError(NOT_A_PROFILE_FILE)
    return manifest


def _free_name(name: str, root: Path) -> str:
    """The profile's name, or "name (2)", "name (3)", ... when a profile here already has it."""
    taken = {info.name.casefold() for info in discover_profiles(root)}
    candidate, attempt = name, 1
    while _sanitize_profile_name(candidate).casefold() in taken:
        attempt += 1
        candidate = f"{name} ({attempt})"
    return candidate


def _write_review_marker(paths: ProfilePaths, config: dict) -> None:
    """The descriptor a journal backup restore leaves (session._open reads it): this copy opens read-only,
    for review, and is never a second home."""
    descriptor = {"version": 1, "status": "requires-enrollment", "source": "profile-file",
                  "profile": config.get("profile"), "generation": config.get("generation"),
                  "source_device": config.get("device"), "preserved_database": paths.db_path.name}
    target = paths.db_path.with_name(paths.db_path.name + ".journal-restore.json")
    handle_descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(handle_descriptor, "wb") as handle:
        handle.write(json.dumps(descriptor, sort_keys=True).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())


def read_profile_file(path: str | Path, password: str, root: str | Path) -> OpenedProfile:
    """Check a profile file and publish it under ``root`` as a new profile folder, never over an existing one.

    Nothing is created unless the password opens the key file and the database verifies; a failure leaves
    no new folder.
    """
    from .restore import EncryptedBackupRestorer

    path, root = Path(path), Path(root)
    try:
        if path.is_symlink() or not path.is_file():
            raise ProfileError(NOT_A_PROFILE_FILE)
        if path.stat().st_size > MAX_BYTES:
            raise ProfileError(TOO_LARGE)
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ProfileError(NOT_A_PROFILE_FILE) from exc
    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".open-profile-file-{secrets.token_hex(12)}"
    created: Path | None = None
    try:
        with archive:
            try:
                members = _checked_members(archive)
                manifest = _manifest(_small(archive, members[_MANIFEST]))
                keys = _small(archive, members[_KEYS])
                if hashlib.sha256(keys).hexdigest() != manifest["sha256"][_KEYS]:
                    raise ProfileError(DAMAGED)
                try:
                    document = json.loads(keys)
                    validate_key_file(document)
                except ValueError as exc:
                    raise ProfileError(DAMAGED) from exc
                try:
                    key = unwrap_key(document, password)
                except ValueError as exc:
                    raise ProfileError(WRONG_PASSWORD) from exc
                staging.mkdir(mode=0o700)
                candidate = staging / _DATABASE
                digest, size = hashlib.sha256(), 0
                descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as target, archive.open(members[_DATABASE]) as source:
                    for block in iter(lambda: source.read(_BLOCK), b""):
                        size += len(block)
                        if size > MAX_BYTES:
                            raise ProfileError(TOO_LARGE)
                        digest.update(block)
                        target.write(block)
                    target.flush()
                    os.fsync(target.fileno())
                if digest.hexdigest() != manifest["sha256"][_DATABASE]:
                    raise ProfileError(DAMAGED)
            except (zipfile.BadZipFile, EOFError, NotImplementedError, RuntimeError) as exc:
                raise ProfileError(DAMAGED) from exc
        try:
            EncryptedBackupRestorer._verify_file(candidate, key)
            probe = Database(candidate, key=key, read_only=True)
            try:
                journal = probe.has_table("journal_meta")
                config = json.loads(probe.scalar("SELECT config FROM journal_meta WHERE id=1")) if journal else {}
            finally:
                probe.close()
            if not journal:
                # A review copy stays byte-for-byte what its home saved; an ordinary book is brought up to date.
                EncryptedBackupRestorer._migrate_candidate(candidate, key)
                EncryptedBackupRestorer._verify_file(candidate, key)
        except ProfileError:
            raise
        except Exception as exc:
            raise ProfileError(UNREADABLE_DATABASE) from exc
        name = _free_name(manifest["name"].strip(), root)
        paths = create_profile(name, root=root)
        paths.prepare()  # exclusive: a folder that exists is never reused
        created = paths.data_dir
        publish_keys(paths, document, replace=False)
        if journal:
            _write_review_marker(paths, config if isinstance(config, dict) else {})
        publish_new(candidate, paths.db_path)
        _fsync_directory(paths.data_dir)
        created = None
        return OpenedProfile(paths, paths.profile.name, journal)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if created is not None:
            shutil.rmtree(created, ignore_errors=True)
