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
        assert inspection.current_version == BUNDLED_LATEST_VERSION == 68
        assert inspection.pending == ()
        assert db.scalar("SELECT count(*) FROM transactions") == 68
        assert db.scalar("SELECT count(*) FROM ledger_entries") > 0
        assert db.scalar("PRAGMA integrity_check") == "ok"

        # Undo capture is TEMP-only, even when prepared against the encrypted profile.
        UndoService(db).prepare(db.conn)
        assert db.scalar("SELECT count(*) FROM sqlite_temp_master WHERE name='undo_groups'") == 1
        assert db.scalar("SELECT count(*) FROM sqlite_master WHERE name LIKE 'undo_%'") == 0
    finally:
        db.close()
