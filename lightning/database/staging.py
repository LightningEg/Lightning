"""Explicit import/recovery preparation. Never replace or migrate the source.

These helpers produce verified encrypted candidates only, not live restores.
The future session controller must lock the destination profile, quiesce work,
back up live data and promote the candidate after the user's confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from uuid import uuid4

from lightning.core.dates import wall_now

from .connection import Database
from .migrator import inspect_schema
from .snapshot import export_snapshot


@dataclass(frozen=True)
class StagedDatabase:
    path: Path
    schema_version: int


def stage_database(source: Path, folder: Path, *, destination_key: bytes,
                   source_key: bytes | None = None) -> StagedDatabase:
    """Stage a consistent encrypted copy for explicit legacy import or recovery.

    A None source_key means explicitly selected legacy plaintext, never an
    automatic fallback after a wrong key. The old app should be closed first;
    the SQLite read transaction includes committed WAL data without stripping
    journals. Incomplete candidates have a recognizable .partial suffix.
    """
    if not isinstance(destination_key, bytes) or len(destination_key) != 32:
        raise ValueError("The destination key must be exactly 32 bytes")
    source, folder = Path(source).resolve(strict=True), Path(folder).resolve()
    db = Database(source, key=source_key, read_only=True)
    if source_key is None:
        # SQLCipher can read plaintext and export directly to encryption.
        # The regular browser Database continues to use stock SQLite.
        from sqlcipher3 import dbapi2
        db.driver = dbapi2
    try:
        if not db.has_table("schema_migrations"):
            raise ValueError("The selected file is not a recognized Lightning database")
        inspection = inspect_schema(db)
        folder.mkdir(parents=True, exist_ok=True)
        day = wall_now(timezone.utc).strftime("%Y-%m-%d")
        sequence = 1 + len(list(folder.glob(f"Import_{day}_*.partial")))
        target = folder / f"Import_{day}_{sequence:03d}_{uuid4().hex}.partial"
        export_snapshot(db.conn, target, key=destination_key, source_encrypted=source_key is not None)
        return StagedDatabase(target, inspection.current_version)
    finally:
        db.close()
