"""Restartable journal-home migration barrier for ledger schema upgrades.

The caller holds the profile instance/session lock. Migration never starts until
an encrypted pre-upgrade snapshot is verified; the durable marker remains until
the upgraded capabilities and checkpoint have been published.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from lightning.database.backup import backup
from lightning.database.connection import Database
from lightning.database.migrator import inspect_schema, migrate
from lightning.database.snapshot import verify_connection

from .codec import JournalError, canonical, fields, hash_value, number

_BARRIER = "upgrade_barrier"


def _hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _barrier(db):
    if not db.has_table("journal_local"):
        raise JournalError("Journal upgrade state is missing; keep the profile locked for repair")
    raw = db.scalar("SELECT value FROM journal_local WHERE name=?", (_BARRIER,))
    if raw is None:
        return None
    try:
        state = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise JournalError("Journal upgrade state is damaged; keep the profile locked for repair") from error
    try:
        fields(state, ("version", "backup", "backup_sha256", "from_schema", "pending"))
        if state["version"] != 1 or type(state["backup"]) is not str or Path(state["backup"]).name != state["backup"]:
            raise ValueError
        hash_value(state["backup_sha256"])
        number(state["from_schema"], minimum=0)
        if type(state["pending"]) is not list or any(type(item) is not str for item in state["pending"]):
            raise ValueError
    except (JournalError, ValueError, TypeError) as error:
        raise JournalError("Journal upgrade state is damaged; keep the profile locked for repair") from error
    return state


def upgrade_profile(paths, key: bytes) -> dict | None:
    """Back up and apply pending migrations before the runtime builds a journal profile.

    Returns a durable barrier descriptor that must be completed after attach and
    checkpoint publication. A returned descriptor means confirmation stays
    blocked across restart until `complete_upgrade` succeeds.
    """
    db = Database(paths.db_path, key=key)
    try:
        verify_connection(db.conn, encrypted=True)
        if not db.has_table("journal_meta"):
            raise JournalError("This profile has no journal upgrade path")
        config = json.loads(db.scalar("SELECT config FROM journal_meta WHERE id=1"))
        state = _barrier(db)
        inspection = inspect_schema(db)
        if state is None and not inspection.pending:
            return None
        if config.get("role") != "home":
            raise JournalError("Only the journal home can migrate the ledger schema")
        if state is None:
            saved = backup(db, paths.backups_dir, pre_upgrade=True)
            if saved is None or not saved.is_file() or saved.is_symlink():
                raise JournalError("A verified pre-upgrade backup is required")
            check = Database(saved, key=key, read_only=True)
            try:
                verify_connection(check.conn, encrypted=True)
            finally:
                check.close()
            state = dict(version=1, backup=saved.name, backup_sha256=_hash(saved),
                         from_schema=inspection.current_version, pending=list(inspection.pending))
            with db.transaction():
                db.execute("INSERT INTO journal_local(name,value) VALUES(?,?)", (_BARRIER, canonical(state).decode()))
        else:
            saved = Path(paths.backups_dir) / state["backup"]
            if saved.is_symlink() or not saved.is_file() or _hash(saved) != state.get("backup_sha256"):
                raise JournalError("The retained pre-upgrade backup is missing or changed")
        migrate(db)
        verify_connection(db.conn, encrypted=True)
        remaining = inspect_schema(db)
        if remaining.pending:
            raise JournalError("Journal migration remains incomplete; keep the profile locked")
        # Ensure every synchronized table can be represented after migration.
        from .effects import Replicator
        Replicator(db, config["profile"]).fingerprint(cached=False)
        return state
    finally:
        db.close()


def complete_upgrade(store, signer, checkpoint_folder, publish_checkpoint=None) -> dict | None:
    """Publish the upgraded peer contract/checkpoint, then release confirmation."""
    state = _barrier(store.db)
    if state is None:
        return None
    if store.config.get("role") != "home":
        raise JournalError("Only the journal home can complete a migration barrier")
    if inspect_schema(store.db).pending:
        raise JournalError("Journal migration remains incomplete")
    store.adapter.verify()
    # Persist a signed local checkpoint before releasing the barrier. Unique
    # names make a retry safe after a crash between export and barrier removal.
    from .snapshots import export
    folder = Path(checkpoint_folder)
    if folder.is_symlink():
        raise JournalError("Checkpoint folder is unsafe")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    checkpoint = folder / f"journal-upgrade-{uuid4().hex}.db"
    manifest_wire = export(store, checkpoint, signer)
    manifest = json.loads(manifest_wire)
    manifest_path = checkpoint.with_suffix(".manifest.json")
    temporary = manifest_path.with_name(manifest_path.name + ".partial")
    try:
        with temporary.open("xb") as handle:
            handle.write(manifest_wire)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, manifest_path)
        if os.name != "nt":
            directory_fd = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    result = dict(checkpoint=checkpoint, manifest=manifest_path, body=manifest["body"])
    # Optional carrier publication happens while the durable barrier remains.
    # Failure leaves the local verified checkpoint and barrier for a retry.
    if publish_checkpoint is not None:
        publish_checkpoint(store, result)
    with store.db.transaction():
        store.db.execute("DELETE FROM journal_local WHERE name=?", (_BARRIER,))
    return result
