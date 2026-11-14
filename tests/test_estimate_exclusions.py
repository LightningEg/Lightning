"""NF-12AK2 (#643, owner decisions 2026-11-13): leave one transaction out of estimates. The estimate basis skips an
excluded expense and the refunds and claim receipts linked to it; Cash flow and Spent keep it; the switch is optional,
on the PC and phone edit and under More on add, and undoable; an older profile upgrades."""
from __future__ import annotations

import shutil

import pytest

from lightning.database import migrator
from lightning.database.connection import Database
from lightning.database.seed import seed


@pytest.mark.parametrize("encrypted", [False, True])
def test_an_older_profile_upgrades_and_keeps_its_rows(monkeypatch, tmp_path, encrypted):
    if encrypted:
        pytest.importorskip("sqlcipher3")
    old = tmp_path / "migrations_85"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 85:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db", key=bytes(range(32)) if encrypted else None)
    try:
        migrator.migrate(db)
        seed(db)
        db.execute("INSERT INTO transactions(ref,type,date,status,description,created_at,updated_at) "
                   "VALUES('OUT-0001','OUT','2026-09-02','POSTED','Laptop','2026-09-02','2026-09-02')")
        before = [dict(r) for r in db.all("SELECT * FROM transactions")]
        monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
        assert migrator.migrate(db) == ["0086_budget_estimate_exclusions (APPLIED)"]
        assert [dict(r) for r in db.all("SELECT * FROM transactions")] == before
        assert db.scalar("SELECT count(*) FROM budget_estimate_exclusions") == 0
        txn = before[0]["id"]
        db.execute("INSERT INTO budget_estimate_exclusions(transaction_id,created_at,updated_at) VALUES(?,?,?)",
                   (txn, "2026-11-14", "2026-11-14"))
        with pytest.raises(Exception):  # one row per transaction
            db.execute("INSERT INTO budget_estimate_exclusions(transaction_id,created_at,updated_at) VALUES(?,?,?)",
                       (txn, "2026-11-14", "2026-11-14"))
        assert migrator.migrate(db) == []  # a second run does nothing
        assert db.scalar("SELECT max(version) FROM schema_migrations") == 86
    finally:
        db.close()
