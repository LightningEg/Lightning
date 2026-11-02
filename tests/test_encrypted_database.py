"""Only disposable data: shared services, backup safety and encrypted storage."""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from lightning.bootstrap import build
from lightning.database.backup import backup
from lightning.database.connection import Database
from lightning.database.snapshot import snapshot

KEY = bytes(range(32))  # Public test key, never used outside scratch fixtures.


def test_full_sample_household_balances_survive_encrypted_backup(tmp_path, monkeypatch):
    from datetime import date
    from decimal import Decimal
    from lightning.demo import build_demo
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    c = build(tmp_path / "Household.db", key=KEY)
    day = date(2026, 9, 30)
    assert build_demo(c, as_of=day)["accounts"] == 7
    expected = c.position.at(day)
    assert expected.holdings_value == Decimal("177902.50")   # CD included
    assert expected.held_for_others == 10000
    assert expected.loans_still_to_pay == 52500
    assert expected.net_worth == expected.what_you_own - expected.what_you_owe
    assert expected.free_cash == expected.cash_you_own - expected.kept_apart - expected.reserves - expected.bills_due
    saved = c.backup_now()
    c.db.close()
    restored = build(saved, key=KEY)
    actual = restored.position.at(day)
    for field in ("net_worth", "free_cash", "holdings_value", "held_for_others", "loans_still_to_pay"):
        assert getattr(actual, field) == getattr(expected, field)
    restored.db.close()


def test_encrypted_finance_roundtrip_and_backup(tmp_path):
    path = tmp_path / "أسرة personal.db"
    c = build(path, key=KEY)
    account = c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1250.50")
    assert c.reporting.account_balance(account.id) == 1250.5
    saved = c.backup_now()
    assert saved and saved.is_file()
    c.db.close()
    assert not path.read_bytes().startswith(b"SQLite format 3")
    for filename in (path, saved):
        reopened = build(filename, key=KEY)
        assert reopened.reporting.account_balance(account.id) == 1250.5
        reopened.db.close()
        standard = sqlite3.connect(filename)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                standard.execute("SELECT * FROM accounts").fetchall()
        finally:
            standard.close()


def test_freed_memory_is_not_wiped_by_owner_decision(tmp_path):
    # Process-wide in SQLCipher, and once on it cannot be turned off; it made ledger reads 3x slower.
    db = Database(tmp_path / "x.db", key=KEY)
    try:
        assert db.scalar("PRAGMA cipher_memory_security") in ("0", 0)
    finally:
        db.close()


def test_wrong_key_never_modifies_existing_database(tmp_path):
    path = tmp_path / "x.db"
    c = build(path, key=KEY)
    c.db.close()
    original = path.read_bytes()
    from sqlcipher3 import dbapi2
    with pytest.raises(dbapi2.DatabaseError):
        build(path, key=bytes(32))
    assert path.read_bytes() == original
    assert not (tmp_path / "backups").exists()


def test_plaintext_never_converts_implicitly(tmp_path):
    path = tmp_path / "legacy.db"
    c = build(path)
    c.db.close()
    original = path.read_bytes()
    from sqlcipher3 import dbapi2
    with pytest.raises(dbapi2.DatabaseError):
        build(path, key=KEY)
    assert path.read_bytes() == original


def test_thread_ownership_close_and_nested_rollback(tmp_path):
    db = Database(tmp_path / "x.db", key=KEY)
    db.execute("CREATE TABLE sample (value INTEGER)")
    with db.transaction():
        db.execute("INSERT INTO sample VALUES (1)")
        with pytest.raises(ValueError), db.transaction():
            db.execute("INSERT INTO sample VALUES (2)")
            raise ValueError("rollback nested")
    assert db.scalar("SELECT sum(value) FROM sample") == 1
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(RuntimeError, match="owning thread"):
            pool.submit(db.scalar, "SELECT 1").result()
    db.close()
    db.close()
    assert not any(db._key)
    with pytest.raises(RuntimeError, match="closed"):
        db.scalar("SELECT 1")


@pytest.mark.parametrize("key", [b"", b"short", "a" * 32, bytes(33)])
def test_invalid_keys_cannot_fall_back_to_plaintext(tmp_path, key):
    with pytest.raises(ValueError):
        Database(tmp_path / "x.db", key=key)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("key", [None, KEY])
def test_backup_rejects_bad_integrity_and_cleans_partial(tmp_path, monkeypatch, key):
    db = Database(tmp_path / "x.db", key=key)
    db.execute("CREATE TABLE sample (value INTEGER)")
    from lightning.database import snapshot as snapshots
    def fail(*args, **kwargs):
        raise ValueError("injected integrity failure")
    monkeypatch.setattr(snapshots, "verify_connection", fail)
    with pytest.raises(ValueError, match="injected"):
        backup(db, tmp_path / "backups")
    assert list((tmp_path / "backups").iterdir()) == []
    assert db.scalar("SELECT count(*) FROM sample") == 0
    db.close()


def test_snapshot_never_overwrites_destination(tmp_path):
    db = Database(tmp_path / "x.db", key=KEY)
    db.execute("CREATE TABLE sample (value INTEGER)")
    target = tmp_path / "keep.db"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        snapshot(db, target)
    assert target.read_bytes() == b"keep"
    db.close()


def test_encrypted_backup_preserves_deleted_autoincrement_high_watermark(tmp_path):
    db = Database(tmp_path / "x.db", key=KEY)
    db.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT)")
    db.execute("INSERT INTO sample(value) VALUES ('keep'), ('deleted')")
    db.execute("DELETE FROM sample WHERE id=2")
    saved = backup(db, tmp_path / "backups")
    reopened = Database(saved, key=KEY)
    reopened.execute("INSERT INTO sample(value) VALUES ('next')")
    assert reopened.scalar("SELECT max(id) FROM sample") == 3
    reopened.close()
    db.close()


def test_upgrade_backup_is_retained_and_failure_blocks_migration(tmp_path, monkeypatch):
    from lightning.database import migrator
    from lightning import bootstrap
    resources = tmp_path / "migrations"
    resources.mkdir()
    (resources / "0001_test.sql").write_text("CREATE TABLE sample(value INTEGER);", encoding="utf8")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", resources)
    db = Database(tmp_path / "x.db", key=KEY)
    migrator.migrate(db)
    db.close()
    original = (tmp_path / "x.db").read_bytes()
    (resources / "0002_more.sql").write_text("ALTER TABLE sample ADD COLUMN more TEXT;", encoding="utf8")
    def fail(*args, **kwargs):
        raise OSError("injected backup failure")
    monkeypatch.setattr(bootstrap, "backup", fail)
    with pytest.raises(OSError, match="backup failure"):
        build(tmp_path / "x.db", key=KEY)
    assert (tmp_path / "x.db").read_bytes() == original
    db = Database(tmp_path / "x.db", key=KEY)
    retained = backup(db, tmp_path / "backups", pre_upgrade=True)
    first = backup(db, tmp_path / "backups", keep=1)
    second = backup(db, tmp_path / "backups", keep=1)
    assert retained.exists() and second.exists() and not first.exists()
    db.close()


def test_newer_schema_rejected_before_backup_or_seed(tmp_path):
    db = build(tmp_path / "x.db", key=KEY).db
    db.execute("INSERT INTO schema_migrations VALUES(9999,'future','APPLIED','future')")
    db.close()
    original = (tmp_path / "x.db").read_bytes()
    with pytest.raises(ValueError, match="newer or unknown"):
        build(tmp_path / "x.db", key=KEY, backup_on_start=True)
    assert (tmp_path / "x.db").read_bytes() == original
    assert not (tmp_path / "backups").exists()


def test_backup_names_sequences_and_profile_isolation(tmp_path):
    from lightning.database.backup import list_backups
    import re
    first = Database(tmp_path / "Personal_2026-09-30_001_a1b2c3d4.db", key=KEY)
    second = Database(tmp_path / "Business_2026-09-30_001_b1b2c3d4.db", key=KEY)
    for db in (first, second):
        db.execute("CREATE TABLE sample(value INTEGER)")
    folder = tmp_path / "backups"
    personal1 = backup(first, folder, keep=1)
    business = backup(second, folder, keep=1)
    personal2 = backup(first, folder, keep=1)
    assert re.fullmatch(r"Personal_2026-09-30_001_a1b2c3d4_backup_\d{4}-\d{2}-\d{2}_002_[0-9a-f]{8}\.db", personal2.name)
    assert not personal1.exists() and personal2.exists() and business.exists()
    assert [entry.path for entry in list_backups(folder, first.path)] == [personal2]
    first.close()
    second.close()


def test_backup_cleanup_does_not_delete_unowned_partial(tmp_path, monkeypatch):
    from importlib import import_module
    module = import_module("lightning.database.backup")
    db = Database(tmp_path / "x.db", key=KEY)
    db.execute("CREATE TABLE sample(value INTEGER)")
    def collision(db, target):
        target.write_bytes(b"another operation")
        raise FileExistsError(target)
    monkeypatch.setattr(module, "snapshot", collision)
    with pytest.raises(FileExistsError):
        backup(db, tmp_path / "backups")
    assert [p.read_bytes() for p in (tmp_path / "backups").iterdir()] == [b"another operation"]
    db.close()
