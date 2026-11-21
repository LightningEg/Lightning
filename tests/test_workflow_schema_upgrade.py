"""The encrypted round-trip profile stays current and action history remains connection-local."""
from __future__ import annotations

import json
from pathlib import Path

from lightning.database.connection import Database
from lightning.database.migrator import BUNDLED_LATEST_VERSION, inspect_schema
from lightning.runtime.roundtrip import PASSWORD
from lightning.security.keys import unwrap_key
from lightning.undo import UndoService

FIXTURE = Path(__file__).parent / "fixtures" / "roundtrip"


def test_encrypted_roundtrip_fixture_is_current_and_keeps_its_transactions_out_of_undo_schema():
    keys = json.loads((FIXTURE / "keys.json").read_text(encoding="utf-8"))
    db = Database(FIXTURE / "profile.db", key=unwrap_key(keys, PASSWORD), read_only=True)
    try:
        inspection = inspect_schema(db)
        assert inspection.current_version == BUNDLED_LATEST_VERSION
        assert inspection.pending == ()
        assert db.scalar("SELECT count(*) FROM transactions") == 74
        assert db.scalar("SELECT count(*) FROM ledger_entries") > 0
        assert db.scalar("PRAGMA integrity_check") == "ok"

        # Undo capture is TEMP-only, even when prepared against the encrypted profile.
        UndoService(db).prepare(db.conn)
        assert db.scalar("SELECT count(*) FROM sqlite_temp_master WHERE name='undo_groups'") == 1
        assert db.scalar("SELECT count(*) FROM sqlite_master WHERE name LIKE 'undo_%'") == 0
    finally:
        db.close()


def test_work_refund_reporting_upgrades_existing_claims_and_ledger(tmp_path, monkeypatch):
    from shutil import copytree, ignore_patterns

    from lightning.bootstrap import build
    from lightning.core.dates import parse_month
    from lightning.database import migrator

    previous_migrations = tmp_path / "migration-89"
    copytree(migrator.MIGRATIONS_DIR, previous_migrations, ignore=ignore_patterns("0090_*.sql"))
    profile = tmp_path / "work-refund.db"
    with monkeypatch.context() as old_schema:
        old_schema.setattr(migrator, "MIGRATIONS_DIR", previous_migrations)
        c = build(profile)
        try:
            assert inspect_schema(c.db).current_version == 89
            account = c.account_flows.open_account("Sample cash", "CASH", "2026-09-01", "50000")
            work = c.categories.get_by_code("EXP.WORK.TRANSPORT").id
            expense = c.transactions.record_outflow("2026-09-15", account.id, "1000", work)
            claim = c.reimbursements.create_claim(expense.id, "1000")
            c.reimbursements.mark_paid_for_work(claim["id"])
            c.refunds.record_refund(expense.id, "2026-10-08", "400")
            ledger = [tuple(row) for row in c.db.all("SELECT * FROM ledger_entries ORDER BY transaction_id,line_no")]
        finally:
            c.db.close()

    c = build(profile)
    try:
        assert inspect_schema(c.db).current_version == 90
        assert migrator.migrate(c.db) == []
        assert [tuple(row) for row in c.db.all("SELECT * FROM ledger_entries ORDER BY transaction_id,line_no")] == ledger
        assert c.reimbursements.list_claims()[0]["outstanding"] == 600
        assert c.budgets.owned_spending(*parse_month("2026-10")).get(work, 0) == 0
    finally:
        c.db.close()
