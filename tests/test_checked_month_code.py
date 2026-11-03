"""IT-9K: the checked-month refusal carries a code (migration 0069), the database layer matches the code, and a
profile created before the migration is upgraded in place."""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from lightning.core.errors import ValidationError
from lightning.database import migrator
from lightning.database.connection import CHECKED_MONTH_CODE, CHECKED_MONTH_MESSAGE, Database
from lightning.ui.i18n import translate

TRIGGERS = ("checked_ledger_insert", "checked_ledger_update", "checked_ledger_delete",
            "checked_transaction_update", "checked_transaction_delete")


def _old_profile(monkeypatch, tmp_path) -> Database:
    """A profile at schema 68, the version before the code existed."""
    old = tmp_path / "migrations_68"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 68:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db")
    migrator.migrate(db)
    assert migrator.inspect_schema(db).current_version == 68
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
    return db


def _refusal(db: Database) -> str:
    db.conn.execute("PRAGMA foreign_keys=OFF")  # an empty profile has no account 1; only the trigger is under test
    db.execute("INSERT INTO reconciled_through(account_id,date,bank_balance_e6,checked_at) VALUES(1,'2026-10-01',0,'x')")
    with pytest.raises(sqlite3.IntegrityError) as error:
        db.execute("INSERT INTO ledger_entries(account_id,date) VALUES(1,'2026-09-15')")
    return str(error.value)


def test_upgrade_recreates_the_five_triggers_with_the_code(monkeypatch, tmp_path):
    db = _old_profile(monkeypatch, tmp_path)
    assert CHECKED_MONTH_CODE not in _refusal(db)  # the old message had no code
    db.execute("DELETE FROM reconciled_through")
    assert migrator.inspect_schema(db).pending[0] == "0069_checked_month_code"
    migrator.migrate(db)
    assert migrator.inspect_schema(db).current_version == migrator.BUNDLED_LATEST_VERSION
    names = {row[0] for row in db.all("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'checked_%'")}
    assert names == set(TRIGGERS)
    for name in TRIGGERS:
        assert f"[{CHECKED_MONTH_CODE}]" in db.scalar("SELECT sql FROM sqlite_master WHERE name=?", (name,))
    assert f"[{CHECKED_MONTH_CODE}]" in _refusal(db)
    db.close()


def test_a_checked_month_refusal_becomes_a_validation_error_by_its_code(c, setup):
    accounts, cats = setup
    account_id = accounts["cib"].id
    c.reconciliation.close(account_id, "2026-10-01", c.reconciliation.balance(account_id, "2026-10-01"))
    with pytest.raises(ValidationError) as error:
        c.transactions.record_outflow("2026-10-01", account_id, "20", cats["EXP.PERSONAL.FOOD"].id)
    assert str(error.value) == CHECKED_MONTH_MESSAGE
    assert CHECKED_MONTH_MESSAGE.endswith(f"[{CHECKED_MONTH_CODE}]")


def test_the_message_reads_in_arabic():
    assert translate(CHECKED_MONTH_MESSAGE, "ar").startswith("الشهر ده اتراجع مع البنك")
    assert not any(ch.isascii() and ch.isalpha() for ch in translate(CHECKED_MONTH_MESSAGE, "ar").replace(CHECKED_MONTH_CODE, ""))
