"""BT-2AI2: one `.lightning` file carries an encrypted profile from a PC to a phone with no network and no pairing.

The file is a zip of exactly three members: `manifest.json` (format, name, creation day, identity, hashes),
`profile.db` (a verified encrypted copy of the ledger) and `keys.json` (the password-wrapped key, never the key
itself). Opening it checks the shape, the hashes and the password-unwrapped key against the database before a
single file reaches the profile folder, so a damaged or foreign file leaves the phone exactly as it was.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from lightning.database.backup import backup
from lightning.database.connection import Database
from lightning.runtime.paths import ProfileInfo, ProfilePaths, create_profile, discover_profiles
from lightning.runtime.restore import EncryptedBackupRestorer
from lightning.runtime.session import ProfileError, read_slot
from lightning.security.keys import unwrap_key

FORMAT = "lightning-profile-file"
VERSION = 1
SUFFIX = ".lightning"
MAX_BYTES = 64 * 1024 * 1024  # a ledger is megabytes; this only stops a runaway file
_MEMBERS = {"manifest.json", "profile.db", "keys.json"}
_MANIFEST_KEYS = {"format", "version", "name", "created", "profile_id", "db_sha256", "keys_sha256"}
_ID = re.compile(r"[0-9a-f]{8}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_profile_file(paths: ProfilePaths, db: Database, destination: Path) -> Path:
    """Write the open profile as one file at `destination` (replacing nothing: the name must be free)."""
    info = paths.profile
    if info is None:
        raise ProfileError("Only a named profile can be exported.")
    destination = Path(destination)
    if destination.exists():
        raise ProfileError("A file with that name already exists.")
    with tempfile.TemporaryDirectory(prefix=".lightning-export-", dir=destination.parent) as scratch:
        copy = backup(db, scratch, keep=0)
        if copy is None:
            raise ProfileError("Could not make a verified copy of this profile; nothing was exported.")
        manifest = {"format": FORMAT, "version": VERSION, "name": info.name, "created": info.created.isoformat(),
                    "profile_id": info.profile_id, "db_sha256": _sha256(copy),
                    "keys_sha256": _sha256(paths.keys_path)}
        partial = destination.with_suffix(destination.suffix + ".partial")
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED) as archive:  # the database is already encrypted
            archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
            archive.write(copy, "profile.db")
            archive.write(paths.keys_path, "keys.json")
        os.replace(partial, destination)
    return destination


def _read_manifest(archive: zipfile.ZipFile) -> dict:
    names = [item.filename for item in archive.infolist()]
    if sorted(names) != sorted(_MEMBERS):
        raise ProfileError("This is not a Lightning profile file.")
    if sum(item.file_size for item in archive.infolist()) > MAX_BYTES:
        raise ProfileError("This profile file is larger than Lightning will open.")
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ProfileError("This is not a Lightning profile file.") from exc
    if (not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS or manifest["format"] != FORMAT
            or not isinstance(manifest["version"], int)):
        raise ProfileError("This is not a Lightning profile file.")
    if manifest["version"] > VERSION:
        raise ProfileError("This profile file was made by a newer Lightning. Update this app and try again.")
    if (not isinstance(manifest["name"], str) or not manifest["name"].strip()
            or not isinstance(manifest["profile_id"], str) or not _ID.fullmatch(manifest["profile_id"])):
        raise ProfileError("This profile file is damaged.")
    try:
        date.fromisoformat(manifest["created"])
    except (TypeError, ValueError) as exc:
        raise ProfileError("This profile file is damaged.") from exc
    return manifest


def open_profile_file(root: Path, source: Path, password: str) -> ProfileInfo:
    """Check `source` and the password, then add it to `root` as a new profile. Nothing is written unless every
    check passes; a profile with the same identity already there is never replaced."""
    root = Path(root)
    try:
        archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ProfileError("This is not a Lightning profile file.") from exc
    with archive:
        manifest = _read_manifest(archive)
        if any(manifest["profile_id"] == info.profile_id for info in discover_profiles(root)):
            raise ProfileError("This profile is already on this device. Unlock it from the profile list.")
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".lightning-open-", dir=root) as scratch:
            staged = Path(scratch)
            for member in ("profile.db", "keys.json"):
                with archive.open(member) as read, (staged / member).open("wb") as write:
                    shutil.copyfileobj(read, write)
            if _sha256(staged / "profile.db") != manifest["db_sha256"] or \
                    _sha256(staged / "keys.json") != manifest["keys_sha256"]:
                raise ProfileError("This profile file is damaged: its contents do not match.")
            try:
                key = unwrap_key(read_slot(staged / "keys.json"), password)
            except (ProfileError, ValueError) as exc:
                raise ProfileError("The profile password could not unlock this file.") from exc
            try:
                EncryptedBackupRestorer._verify_file(staged / "profile.db", key)
            except Exception as exc:
                raise ProfileError("This profile file is damaged, or needs a newer Lightning version.") from exc
            created = datetime.fromisoformat(manifest["created"]).replace(tzinfo=timezone.utc)
            paths = create_profile(manifest["name"], root=root, created_at=created,
                                   id_factory=lambda: manifest["profile_id"])
            paths.prepare()
            try:
                os.replace(staged / "keys.json", paths.keys_path)
                os.replace(staged / "profile.db", paths.db_path)
            except BaseException:
                shutil.rmtree(paths.data_dir, ignore_errors=True)  # a half-made folder must not look like a profile
                raise
    return paths.profile
