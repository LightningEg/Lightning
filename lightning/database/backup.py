"""Verified, uniquely named backups; pre-upgrade copies are never pruned."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .connection import Database
from .snapshot import snapshot


@dataclass(frozen=True)
class BackupFile:
    path: Path
    date: str
    sequence: int
    identifier: str
    pre_upgrade: bool


def list_backups(folder: str | Path, database: str | Path) -> list[BackupFile]:
    """List only this database's completed backups without opening/decrypting them."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    pattern = re.compile(re.escape(Path(database).stem) +
                         r"_(backup|upgrade)_(\d{4}-\d{2}-\d{2})_(\d{3,})_([0-9a-f]{8})\.db$")
    found = []
    for path in folder.iterdir():
        match = pattern.fullmatch(path.name)
        if match and path.is_file() and not path.is_symlink():
            kind, day, sequence, identifier = match.groups()
            found.append(BackupFile(path, day, int(sequence), identifier, kind == "upgrade"))
    return sorted(found, key=lambda entry: (entry.date, entry.sequence, entry.path.name), reverse=True)


def _today() -> str:
    """The day in backup file names (UTC), so "one a day" and the names agree."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def backed_up_today(folder: str | Path, database: str | Path) -> bool:
    """Whether this database already has a backup (not a pre-upgrade copy) dated today."""
    return any(not entry.pre_upgrade and entry.date == _today() for entry in list_backups(folder, database))


def backup(db: Database, folder: str | Path, keep: int = 30, *,
           pre_upgrade: bool = False, verify_source: bool = True) -> Path | None:
    """A verified encrypted copy. `verify_source=False` skips the source integrity check only when the caller
    has just verified the same file (an unlock); the copy is always checked."""
    if db.path == ":memory:" or not Path(db.path).exists():
        return None
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    day = _today()
    kind = "upgrade" if pre_upgrade else "backup"
    prefix = f"{Path(db.path).stem}_{kind}_{day}_"
    # Count matching partials too: a crashed attempt must not reuse its sequence.
    pattern = re.compile(re.escape(prefix) + r"(\d{3,})_[0-9a-f]{8}\.(?:db|partial)$")
    sequences = [int(match[1]) for p in folder.iterdir() if (match := pattern.fullmatch(p.name))]
    sequence = max(sequences, default=0) + 1
    target = folder / f"{prefix}{sequence:03d}_{uuid4().hex[:8]}.db"
    staging = target.with_suffix(".partial")
    created = False
    try:
        snapshot(db, staging) if verify_source else snapshot(db, staging, verify_source=False)
        created = True
        if target.exists():
            raise FileExistsError(target)
        os.replace(staging, target)
        if os.name != "nt":
            directory_fd = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        if created:
            staging.unlink(missing_ok=True)
        raise
    backups = [entry.path for entry in list_backups(folder, db.path) if not entry.pre_upgrade]
    for old in backups[keep:] if keep > 0 else []:
        old.unlink(missing_ok=True)
    return target
