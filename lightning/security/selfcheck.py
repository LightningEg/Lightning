"""Synthetic, temporary-only SQLCipher and key-management feasibility checks."""

from __future__ import annotations

import sqlite3
import tempfile
from importlib import resources
from pathlib import Path

from .keys import create_key_file, new_data_key, new_recovery_key, open_with_recovery, unwrap_key, wrap_key


def _key_literal(key: bytes) -> str:
    return f'"x\'{key.hex()}\'"'


def _pragma_ok(connection, name: str) -> bool:
    row = connection.execute(f"PRAGMA {name}").fetchone()
    return bool(row and str(row[0]).lower() == "ok")


def _cipher_integrity_ok(connection) -> bool:
    # SQLCipher reports corrupt pages as rows; a clean database returns none.
    return not connection.execute("PRAGMA cipher_integrity_check").fetchall()


def _resource_checks() -> dict[str, bool]:
    root = Path(__file__).resolve().parents[1]
    checks = {
        "migrations": (root / "database" / "migrations").is_dir()
        and any((root / "database" / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")),
        "templates": (root / "ui" / "templates").is_dir()
        and any((root / "ui" / "templates").rglob("*.html")),
        "static": (root / "ui" / "static").is_dir()
        and any(path.is_file() for path in (root / "ui" / "static").rglob("*")),
        "catalogue": (root / "assets" / "egx_instruments.csv").is_file() and (root / "assets" / "us_instruments.csv").is_file(),
    }
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo("Africa/Cairo")
        checks["timezone"] = any(
            (Path(directory) / "Africa" / "Cairo").is_file()
            for directory in __import__("zoneinfo").TZPATH
        )
        if not checks["timezone"]:
            checks["timezone"] = resources.files("tzdata.zoneinfo").joinpath("Africa", "Cairo").is_file()
    except (ImportError, KeyError, OSError):
        checks["timezone"] = False
    return checks


def run_checks() -> dict[str, bool]:
    """Exercise crypto and SQLCipher exclusively with disposable synthetic files.

    The returned values contain only aggregate proof booleans; no key, password,
    temporary path, database content, or exception details are returned.
    """
    result = {
        "recovery_roundtrip": False,
        "password_roundtrip": False,
        "password_tamper_rejected": False,
        "sqlcipher_raw_key": False,
        "synthetic_database": False,
        "encrypted_backup": False,
        "wrong_key_rejected": False,
        "stdlib_sqlite_rejected": False,
        "integrity_check": False,
        "cipher_integrity_check": False,
    }
    resources = _resource_checks()
    result.update({f"resource_{name}": passed for name, passed in resources.items()})
    try:
        import sqlcipher3.dbapi2 as cipher
    except ImportError:
        result["ok"] = False
        return result

    try:
        key, recovery_text = new_data_key(), new_recovery_key()
        key_file = create_key_file(key, "synthetic self-check passphrase", recovery_text,
                                   "Synthetic question?", "Synthetic answer")
        result["recovery_roundtrip"] = open_with_recovery(key_file, recovery_text, "SYNTHETIC  answer") == key
        slot = wrap_key(key, "synthetic self-check passphrase")
        result["password_roundtrip"] = unwrap_key(slot, "synthetic self-check passphrase") == key
        tampered = dict(slot)
        tampered["memory_kib"] += 1
        try:
            unwrap_key(tampered, "synthetic self-check passphrase")
        except ValueError:
            result["password_tamper_rejected"] = True

        with tempfile.TemporaryDirectory(prefix="lightning-crypto-check-") as temp_dir:
            database_path = Path(temp_dir) / "synthetic.db"
            backup_path = Path(temp_dir) / "synthetic-backup.db"
            connection = cipher.connect(str(database_path))
            try:
                connection.execute("PRAGMA cipher_log_level = NONE")
                connection.execute(f"PRAGMA key = {_key_literal(key)}")
                connection.execute("CREATE TABLE check_data (value TEXT NOT NULL)")
                connection.execute("INSERT INTO check_data VALUES (?)", ("synthetic-only",))
                connection.commit()
                result["sqlcipher_raw_key"] = bool(connection.execute("PRAGMA cipher_version").fetchone())
                result["synthetic_database"] = connection.execute(
                    "SELECT value FROM check_data"
                ).fetchone() == ("synthetic-only",)
                result["integrity_check"] = _pragma_ok(connection, "integrity_check")
                result["cipher_integrity_check"] = _cipher_integrity_ok(connection)
                # Export a consistent encrypted synthetic snapshot, then reopen
                # it to prove the persisted result rather than the live handle.
                backup_name = str(backup_path).replace("'", "''")
                connection.execute(
                    f"ATTACH DATABASE '{backup_name}' AS synthetic_backup KEY {_key_literal(key)}"
                )
                try:
                    connection.execute("SELECT sqlcipher_export('synthetic_backup')")
                finally:
                    connection.execute("DETACH DATABASE synthetic_backup")
            finally:
                connection.close()

            backup = cipher.connect(str(backup_path))
            try:
                backup.execute("PRAGMA cipher_log_level = NONE")
                backup.execute(f"PRAGMA key = {_key_literal(key)}")
                # The cipher integrity pragma is successful only when it reports no bad pages.
                result["encrypted_backup"] = _pragma_ok(backup, "integrity_check") and _cipher_integrity_ok(
                    backup
                ) and backup.execute("SELECT value FROM check_data").fetchone() == ("synthetic-only",)
            finally:
                backup.close()

            wrong = cipher.connect(str(database_path))
            try:
                wrong.execute("PRAGMA cipher_log_level = NONE")
                wrong.execute(f"PRAGMA key = {_key_literal(bytes(32))}")
                try:
                    row = wrong.execute("SELECT value FROM check_data").fetchone()
                    result["wrong_key_rejected"] = row != ("synthetic-only",)
                except cipher.DatabaseError:
                    result["wrong_key_rejected"] = True
            finally:
                wrong.close()

            standard = sqlite3.connect(str(database_path))
            try:
                try:
                    row = standard.execute("SELECT value FROM check_data").fetchone()
                    result["stdlib_sqlite_rejected"] = row != ("synthetic-only",)
                except sqlite3.DatabaseError:
                    result["stdlib_sqlite_rejected"] = True
            finally:
                standard.close()
    except Exception:
        # Do not expose cryptographic values or local filesystem details in diagnostics.
        pass

    result["ok"] = all(result.values())
    return result
