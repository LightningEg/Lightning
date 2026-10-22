"""Verified snapshots; encrypted sources never pass through a plaintext file.

Only newly created destinations are accepted. Callers hold the profile lock and
must not admit concurrent operations while snapshotting. No live-file restore or
automatic legacy conversion happens here.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from .connection import Database


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def verify_connection(conn, *, encrypted: bool) -> None:
    if [tuple(row) for row in conn.execute("PRAGMA integrity_check")] != [("ok",)]:
        raise ValueError("Database integrity check failed")
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("Database foreign-key check failed")
    if encrypted and conn.execute("PRAGMA cipher_integrity_check").fetchone() is not None:
        raise ValueError("Encrypted page integrity check failed")


def _inventory(conn) -> tuple:
    """Schema plus order-independent row fingerprints (including exact amounts).

    Virtual/shadow index rows can be rebuilt by sqlcipher_export. Compare their
    schema, and fingerprint the underlying application tables instead.
    """
    schema = tuple(tuple(row) for row in conn.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ))
    tables = sorted(row[1] for row in conn.execute("PRAGMA table_list")
                    if row[0] == "main" and row[2] == "table"
                    and not row[1].startswith("sqlite_"))
    data = []
    for table in tables:
        count = total = 0
        for row in conn.execute(f"SELECT * FROM {_quote(table)}"):
            digest = hashlib.sha256()
            for value in row:
                if value is None:
                    tag, encoded = b"n", b""
                elif isinstance(value, bytes):
                    tag, encoded = b"b", value
                elif isinstance(value, str):
                    tag, encoded = b"s", value.encode("utf-8")
                else:
                    tag, encoded = b"v", repr(value).encode("ascii")
                digest.update(tag + len(encoded).to_bytes(8, "big") + encoded)
            count += 1
            total = (total + int.from_bytes(digest.digest(), "big")) % (1 << 256)
        data.append((table, count, total))
    sequence = tuple(tuple(row) for row in conn.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name")) if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'"
    ).fetchone() else ()
    return schema, tuple(data), sequence, conn.execute("PRAGMA user_version").fetchone()[0], conn.execute("PRAGMA application_id").fetchone()[0]


def _remove_partial(target: Path) -> None:
    # Only the exclusive-created output and its SQLite sidecars belong to us.
    for path in (target, Path(str(target) + "-journal"), Path(str(target) + "-wal"), Path(str(target) + "-shm")):
        path.unlink(missing_ok=True)


def export_snapshot(conn, target: Path, *, key: bytes | None = None,
                    source_encrypted: bool = False, verify_source: bool = True) -> Path:
    """Export with SQLCipher when keyed, otherwise use SQLite's backup API.

    Supply a SQLCipher connection when key is provided. Source may be encrypted
    or a read-only legacy database. Reopen output to verify persisted contents.
    `verify_source=False` skips the source integrity check for a caller that has just run it on the same file.
    """
    if key is not None and (not isinstance(key, bytes) or len(key) != 32):
        raise ValueError("The database key must be exactly 32 bytes")
    if source_encrypted and key is None:
        raise ValueError("Encrypted snapshots require a destination key")
    if conn.in_transaction:
        raise RuntimeError("Finish active transactions before taking a snapshot")
    target = Path(target)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    attached = False
    try:
        if key is not None:
            conn.execute(f'ATTACH DATABASE ? AS lightning_copy KEY "x\'{key.hex()}\'"', (str(target),))
            attached = True
            conn.execute("PRAGMA lightning_copy.journal_mode = DELETE")
        conn.execute("BEGIN")
        try:
            # Pins a consistent source snapshot including committed WAL data.
            expected = _inventory(conn)
            if verify_source:
                verify_connection(conn, encrypted=source_encrypted)
            if key is not None:
                conn.execute("SELECT sqlcipher_export('lightning_copy')").fetchone()
                conn.execute(f"PRAGMA lightning_copy.user_version = {int(expected[3])}")
                conn.execute(f"PRAGMA lightning_copy.application_id = {int(expected[4])}")
            else:
                dest = sqlite3.connect(target)
                try:
                    conn.backup(dest)
                finally:
                    dest.close()
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        if attached:
            conn.execute("DETACH DATABASE lightning_copy")
            attached = False
        check = Database(target, key=key, read_only=True)
        try:
            verify_connection(check.conn, encrypted=key is not None)
            if _inventory(check.conn) != expected:
                raise ValueError("Snapshot contents do not match the source")
        finally:
            check.close()
        with target.open("rb+") as stream:
            os.fsync(stream.fileno())
        return target
    except BaseException:
        try:
            if attached:
                conn.execute("DETACH DATABASE lightning_copy")
        finally:
            _remove_partial(target)
        raise


def snapshot(db: Database, target: Path, *, verify_source: bool = True) -> Path:
    db._check_owner()
    return export_snapshot(db.conn, target, key=bytes(db._key) if db.encrypted else None,
                           source_encrypted=db.encrypted, verify_source=verify_source)
