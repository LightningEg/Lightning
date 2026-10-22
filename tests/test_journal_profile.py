"""Exercise profile-session integration at the encrypted database boundary.

These are deliberately lifecycle tests: journal internals have smaller unit
tests, while this file verifies the normal picker/session path owns the same
database and applies the service proxy after conversion.
"""
from __future__ import annotations

import json

import pytest
import shutil
from uuid import uuid4

from lightning.runtime.session import ProfileSession, read_keys
from lightning.sync.journal.backups import create, restore_copy


PASSWORD = "a correct long passphrase"
ANSWER = "El Orman"
RECOVERY = "the recovery key shown during profile setup"


@pytest.fixture(autouse=True)
def inexpensive_owner_wraps(monkeypatch):
    from lightning.sync.journal import owner
    monkeypatch.setattr(owner, "RECOVERY_MEMORY_KIB", 32768)
    monkeypatch.setattr(owner, "RECOVERY_ITERATIONS", 2)


def _profile(tmp_path):
    session = ProfileSession(tmp_path / "Documents" / "Lightning")
    session.prepare("Home", PASSWORD, PASSWORD, "Which school?", ANSWER)
    recovery = session.pending.recovery
    session.confirm(recovery)
    # Cutover starts from a non-empty, ordinary household ledger.
    account = session.container.account_flows.open_account(
        "Current", "BANK", "2026-09-01", "10000", institution="CIB")
    path, account_id = session.paths.db_path, account.id
    session.close()
    return session, path, recovery, account_id


def test_encrypted_existing_profile_cutover_saves_and_reopens_through_session(tmp_path):
    session, path, recovery, account_id = _profile(tmp_path)
    session.unlock(str(path), PASSWORD)
    session.enable_journal(PASSWORD, recovery, ANSWER)
    assert session.journal is not None
    assert session.container.db.scalar("SELECT COUNT(*) FROM accounts WHERE id=?", (account_id,)) == 1

    category = session.container.categories.get_by_code("EXP.WORK.SALARY")
    with session.container.db.transaction():
        session.container.transactions.record_inflow(
            "2026-09-02", account_id, "125", category.id, "salary")
    assert session.container.db.scalar("SELECT COUNT(*) FROM transactions WHERE type!='OPN'") == 1

    session.close()
    session.unlock(str(path), PASSWORD)
    assert session.journal is not None
    assert session.container.db.scalar("SELECT COUNT(*) FROM transactions WHERE type!='OPN'") == 1
    session.close()


def test_current_schema_replica_unlock_does_not_start_upgrade(tmp_path):
    session, path, recovery, _ = _profile(tmp_path)
    session.unlock(str(path), PASSWORD)
    session.enable_journal(PASSWORD, recovery, ANSWER)
    config = json.loads(session.container.db.scalar("SELECT config FROM journal_meta WHERE id=1"))
    config["role"] = "replica"
    with session.container.db.transaction():
        session.container.db.execute("UPDATE journal_meta SET config=? WHERE id=1", (json.dumps(config),))
    session.close()

    session.unlock(str(path), PASSWORD)
    assert session.journal is not None
    assert session.journal.store.config["role"] == "replica"
    assert session.container.db.scalar("SELECT value FROM journal_local WHERE name='upgrade_barrier'") is None
    session.close()


def test_restored_journal_copy_unlocks_as_read_only_quarantine(tmp_path):
    session, path, recovery, _ = _profile(tmp_path)
    session.unlock(str(path), PASSWORD)
    session.enable_journal(PASSWORD, recovery, ANSWER)
    package = tmp_path / "device-backup.db"
    wire = create(session.journal.device, package, key_document=read_keys(session.paths),
                  owner_document=session.journal.owner_document)
    target = tmp_path / "comparison.db"
    restore_copy(package, wire, backup_key=session.sync_key, target=target,
                 new_device=str(uuid4()), new_incarnation=str(uuid4()))
    session.close()

    # Explicit-database profile credentials live in the standard sidecar.
    sidecar = target.parent / f".{target.name}.lightning"
    sidecar.mkdir()
    shutil.copy2(path.parent / "keys.json", sidecar / "keys.json")
    session.unlock(str(target), PASSWORD)
    assert session.role.value == "reader"
    assert session.journal is None
    assert session.container.db.read_only
    session.close()
