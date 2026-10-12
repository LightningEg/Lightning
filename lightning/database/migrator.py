"""Apply numbered SQL migrations atomically and in manifest order."""

from __future__ import annotations

import functools
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightning.core.dates import now_iso

from .connection import Database

_BUNDLED_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BUNDLED_LATEST_VERSION = 53
MIGRATIONS_DIR = _BUNDLED_MIGRATIONS_DIR
_FILE_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_TRANSACTION_RE = re.compile(r"^(?:BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b", re.I)
_COMMENT_RE = re.compile(r"\A(?:\s|--[^\n]*(?:\n|\Z)|/\*.*?\*/)*", re.S)
_OPTIONAL_ERROR_RE = re.compile(r"^no such module:\s*fts5\s*$", re.I)
_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " version INTEGER PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, applied_at TEXT NOT NULL)"
)


@dataclass(frozen=True)
class _Migration:
    version: int
    name: str
    path: Path
    statements: tuple[str, ...]
    optional: bool

    @property
    def filename(self) -> str:
        return f"{self.version:04d}_{self.name}"


@dataclass(frozen=True)
class SchemaInspection:
    """Read-only schema state for callers deciding whether to back up first."""

    current_version: int
    latest_version: int
    pending: tuple[str, ...]

    @property
    def needs_backup(self) -> bool:
        return bool(self.pending)


@functools.lru_cache(maxsize=None)
def _split_sql(sql: str, source: str) -> tuple[str, ...]:
    """Split complete SQLite statements, including trigger bodies. Cached: every database open reads them."""
    statements: list[str] = []
    start = 0
    end = sql.find(";")
    while end != -1:
        if sqlite3.complete_statement(sql[start:end + 1]):
            statement = sql[start:end + 1].strip()
            if _COMMENT_RE.sub("", statement).strip():
                statements.append(statement)
            start = end + 1
        end = sql.find(";", end + 1)
    remainder = sql[start:]
    if remainder.strip():
        body = _COMMENT_RE.sub("", remainder).strip()
        # Comments and whitespace after a terminated statement are not SQL
        # statements themselves. A comments-only resource still fails below.
        if body and not sqlite3.complete_statement(remainder):
            raise ValueError(f"Incomplete SQL statement in migration resource {source}")
        if body:
            statements.append(remainder.strip())
    if not statements:
        raise ValueError(f"Migration resource is empty: {source}")
    for statement in statements:
        body = _COMMENT_RE.sub("", statement).lstrip()
        if _TRANSACTION_RE.match(body):
            raise ValueError(f"Transaction control is not allowed in migration resource {source}")
    return tuple(statements)


def _migration_files() -> list[_Migration]:
    if not MIGRATIONS_DIR.is_dir():
        raise FileNotFoundError(f"Migration resources are missing: {MIGRATIONS_DIR}")
    resources = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not resources:
        raise FileNotFoundError(f"No migration resources found in {MIGRATIONS_DIR}")

    found: dict[int, _Migration] = {}
    for path in resources:
        match = _FILE_RE.fullmatch(path.name)
        if match is None:
            raise ValueError(f"Malformed migration filename: {path.name}")
        version, name = int(match[1]), match[2]
        if version in found:
            raise ValueError(f"Duplicate migration version {version:04d}: {found[version].path.name}, {path.name}")
        sql = path.read_text(encoding="utf-8")
        statements = _split_sql(sql, path.name)
        found[version] = _Migration(
            version, name, path, statements, sql.lstrip().startswith("-- @optional")
        )

    versions = sorted(found)
    expected = list(range(1, versions[-1] + 1))
    if versions != expected:
        missing = sorted(set(expected) - set(versions))
        raise ValueError(f"Migration manifest has version gaps: {', '.join(f'{v:04d}' for v in missing)}")
    if (
        MIGRATIONS_DIR.resolve() == _BUNDLED_MIGRATIONS_DIR.resolve()
        and versions[-1] != BUNDLED_LATEST_VERSION
    ):
        raise ValueError(
            f"Bundled migration manifest ends at {versions[-1]:04d}; "
            f"expected {BUNDLED_LATEST_VERSION:04d}"
        )
    return [found[version] for version in versions]


def _stored_rows(db: Any) -> list[tuple[int, str, str]]:
    conn = db.conn
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if exists is None:
        return []
    columns = {row[1] for row in conn.execute("PRAGMA table_info(schema_migrations)").fetchall()}
    required = {"version", "name", "status", "applied_at"}
    if not required.issubset(columns):
        raise ValueError("schema_migrations is malformed; refusing to modify the database")
    rows = conn.execute("SELECT version, name, status FROM schema_migrations ORDER BY version").fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def _inspect(db: Any) -> tuple[SchemaInspection, list[_Migration]]:
    migrations = _migration_files()
    by_version = {migration.version: migration for migration in migrations}
    stored = _stored_rows(db)
    recorded: dict[int, tuple[str, str]] = {}
    for version, name, status in stored:
        if not isinstance(version, int) or version not in by_version:
            raise ValueError(f"Database schema version {version!r} is newer or unknown; refusing to modify it")
        if version in recorded:
            raise ValueError(f"Duplicate schema_migrations record for version {version:04d}")
        migration = by_version[version]
        if name != migration.name:
            raise ValueError(
                f"Schema migration {version:04d} is named {name!r}, expected {migration.name!r}; refusing to modify it"
            )
        if status not in ("APPLIED", "SKIPPED"):
            raise ValueError(f"Invalid migration status {status!r} for version {version:04d}")
        if status == "SKIPPED" and not migration.optional:
            raise ValueError(f"Required migration {version:04d} is recorded as SKIPPED")
        recorded[version] = (name, status)

    current = max(recorded, default=0)
    pending = tuple(m.filename for m in migrations if m.version not in recorded)
    return SchemaInspection(current, migrations[-1].version, pending), migrations


def inspect_schema(db: Database) -> SchemaInspection:
    """Validate schema state and report pending migrations without writing."""
    inspection, _ = _inspect(db)
    return inspection


def pending_migrations(db: Database) -> tuple[str, ...]:
    """Return pending migration identifiers after read-only validation."""
    return inspect_schema(db).pending


def _is_missing_fts5(exc: Exception) -> bool:
    return bool(_OPTIONAL_ERROR_RE.fullmatch(str(exc).strip()))


def migrate(db: Database) -> list[str]:
    """Apply pending migrations and atomically record each result."""
    # All resource and stored-schema validation, including SQL parsing, happens
    # before creating schema_migrations or making any other database write.
    inspection, migrations = _inspect(db)
    pending_names = set(inspection.pending)
    applied: list[str] = []
    operational_error = getattr(db, "OperationalError", sqlite3.OperationalError)
    for migration in migrations:
        if migration.filename not in pending_names:
            continue
        status = "APPLIED"
        try:
            with db.transaction():
                db.conn.execute(_SCHEMA_SQL)
                for statement in migration.statements:
                    db.conn.execute(statement)
                db.conn.execute(
                    "INSERT INTO schema_migrations(version, name, status, applied_at) VALUES (?,?,?,?)",
                    (migration.version, migration.name, status, now_iso()),
                )
        except operational_error as exc:
            if not migration.optional or not _is_missing_fts5(exc):
                raise
            # The failed transaction has rolled back all DDL. Record only the
            # known unsupported capability in its own transaction.
            status = "SKIPPED"
            with db.transaction():
                db.conn.execute(_SCHEMA_SQL)
                db.conn.execute(
                    "INSERT INTO schema_migrations(version, name, status, applied_at) VALUES (?,?,?,?)",
                    (migration.version, migration.name, status, now_iso()),
                )
        applied.append(f"{migration.filename} ({status})")
    return applied
