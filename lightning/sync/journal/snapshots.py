"""Signed encrypted checkpoints; transactional replica repair preserves local queues."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from lightning.database.connection import Database
from lightning.database.snapshot import snapshot, verify_connection

from .codec import JournalError, ZERO_HASH, authenticate, canonical, cursor as validate_cursor, fields, hash_value, number, seal, unpack
from .finance import inspect_adapter, PARTY
from .store import JournalStore


def _hash(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 200 * 1024 * 1024:
        raise JournalError("Invalid or oversized snapshot")
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _stage(source, folder, expected_hash, expected_size):
    """Bind verification to private staged bytes, not a mutable download path."""
    if source.is_symlink() or not source.is_file() or not 0 < expected_size <= 200 * 1024 * 1024:
        raise JournalError("Invalid or oversized snapshot")
    descriptor, name = tempfile.mkstemp(prefix=".journal-candidate-", suffix=".db", dir=folder)
    target = Path(name)
    result, size = hashlib.sha256(), 0
    try:
        with os.fdopen(descriptor, "wb") as destination, source.open("rb") as incoming:
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                size += len(block)
                if size > expected_size:
                    raise JournalError("Snapshot size mismatch")
                destination.write(block)
                result.update(block)
            destination.flush()
            os.fsync(destination.fileno())
        if size != expected_size or result.hexdigest() != expected_hash:
            raise JournalError("Snapshot hash mismatch")
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def catalog(adapter):
    if getattr(adapter, 'full_domain', False):
        # Full-domain commits include catalog edits. Compatibility describes the
        # contract, rather than requiring equal data before fetching those edits.
        from .domain_schema import SCHEMA_VERSION, TABLES, UNIQUE_KEYS
        from .commands import COMMANDS
        from .codec import digest
        return digest(dict(schema=SCHEMA_VERSION, tables=TABLES,
                           lookups={table: [list(key) for key in keys] for table, keys in UNIQUE_KEYS.items()}, commands=sorted(COMMANDS)))
    result = hashlib.sha256(b"lightning-journal-catalog-v1\n")
    for entity, columns in (("accounts", ("code", "name", "currency", "account_type")),
                            ("categories", ("code", "name", "movement", "is_system")),
                            ("financial_assets", ("code", "currency", "is_cash"))):
        result.update(entity.encode("ascii") + b"\n")
        for row in adapter.db.all(f"SELECT {','.join(columns)} FROM {entity} ORDER BY code"):
            result.update(canonical(dict(row)) + b"\n")
    return result.hexdigest()


def export(store, target, signer):
    if store.config["role"] != "home" or store.adapter is None:
        raise JournalError("Only a financial home exports checkpoints")
    target = Path(target)
    store.db.conn.set_authorizer(None)
    try:
        snapshot(store.db, target)
    finally:
        store.db.conn.set_authorizer(store.adapter._authorize)
    candidate = Database(target, key=store.db.copy_key())
    try:
        saved = JournalStore(candidate)
        adapter = inspect_adapter(candidate, saved.config)
        fingerprint, cursor = adapter.fingerprint(), saved.cursor()
        baseline = catalog(adapter)
        schema = candidate.scalar("SELECT MAX(version) FROM schema_migrations")
        candidate.conn.execute("PRAGMA secure_delete=ON")
        with candidate.transaction():
            for table in ("journal_outbox", "journal_candidates", "journal_seen", "journal_remote_states", "journal_local", "journal_capture_cursor", "journal_batch_undo", "journal_drafts", "journal_candidate_inputs", "journal_mail_in", "journal_mail_out", "journal_rpc", "journal_backup_material", "journal_forms", "journal_form_basis"):
                if candidate.has_table(table):
                    candidate.execute(f"DELETE FROM {table}")
            config = dict(store.config) | {"role": "snapshot"}
            candidate.execute("UPDATE journal_meta SET config=?,next_seq=1 WHERE id=1", (canonical(config).decode(),))
        verify_connection(candidate.conn, encrypted=True)
    finally:
        candidate.close()
    return seal(dict(version=2, type="snapshot", profile=store.config["profile"], generation=store.config["generation"],
                     cursor=cursor, fingerprint=fingerprint, catalog=baseline, schema=schema,
                     size=target.stat().st_size, sha256=_hash(target)), signer)


def repair(store, source, manifest, *, source_key, fault=lambda phase: None, upgrade=False):
    if store.config["role"] != "replica" or store.adapter is None:
        raise JournalError("Only a financial replica can install a checkpoint")
    envelope = unpack(manifest)
    authenticate(envelope, store.config["home_key"])
    body = envelope["body"]
    fields(body, ("version", "type", "profile", "generation", "cursor", "fingerprint", "catalog", "schema", "size", "sha256"))
    store._scope(body)
    validate_cursor(body["cursor"])
    for field in ("fingerprint", "catalog", "sha256"):
        hash_value(body[field])
    number(body["size"], minimum=1)
    number(body["schema"], minimum=1)
    if body["version"] != 2 or body["type"] != "snapshot" or (not upgrade and body["catalog"] != catalog(store.adapter)):
        raise JournalError("Incompatible snapshot or baseline catalog")
    if body["cursor"]["revision"] < store.cursor()["revision"]:
        raise JournalError("A snapshot cannot rewind confirmed authority progress")
    path = _stage(Path(source), Path(store.db.path).parent, body["sha256"], body["size"])
    db = Database(path, key=source_key, read_only=True)
    old_adapter, old_config, upgrading = store.adapter, dict(store.config), False
    try:
        verify_connection(db.conn, encrypted=True)
        if db.scalar("SELECT MAX(version) FROM schema_migrations") != body["schema"] or body["schema"] != store.db.scalar("SELECT MAX(version) FROM schema_migrations"):
            raise JournalError("Snapshot schema mismatch")
        config = json.loads(db.scalar("SELECT config FROM journal_meta WHERE id=1"))
        if config["profile"] != body["profile"] or config["generation"] != body["generation"] or config["role"] != "snapshot":
            raise JournalError("Snapshot identity mismatch")
        if db.scalar("SELECT COUNT(*) FROM journal_outbox") or db.scalar("SELECT COUNT(*) FROM journal_candidates"):
            raise JournalError("A checkpoint must not include another device's local queues")
        adapter = inspect_adapter(db, config)
        if adapter.fingerprint() != body["fingerprint"] or catalog(adapter) != body['catalog']:
            raise JournalError("Snapshot fingerprint mismatch")
        cursor = db.one("SELECT revision,hash FROM journal_commits ORDER BY revision DESC LIMIT 1")
        if (dict(cursor) if cursor else dict(revision=0, hash=ZERO_HASH)) != body["cursor"]:
            raise JournalError("Snapshot cursor mismatch")
        full = getattr(adapter, 'full_domain', False)
        upgrading = upgrade and full and not getattr(store.adapter, 'full_domain', False)
        if upgrade and not full:
            raise JournalError('A domain upgrade requires a full-domain checkpoint')
        if full != getattr(store.adapter, 'full_domain', False) and not upgrading:
            raise JournalError('Snapshot financial contract mismatch')
        transactions = [] if full else [adapter.transaction(row[0]) for row in db.all("SELECT id FROM transactions")]
        # Keep the prior encrypted copy as comparison evidence before changing any
        # domain data. Queue/counter preservation below is a single DB transaction.
        evidence = Path(store.db.path).parent / f".before-journal-repair-{uuid4().hex}.db"
        store.db.conn.set_authorizer(None)
        try:
            snapshot(store.db, evidence)
        finally:
            store.db.conn.set_authorizer(store.adapter._authorize)
        with store.db.transaction():
            if upgrading:
                from .full import enable
                enable(store, _upgrade=True)
                fault('replica_domain_prepared')
            with store.adapter.writing():
                if full:
                    if upgrading:
                        # Legacy replay had no stable posting-line UUIDs and
                        # replaced their local row IDs independently. Rebuild
                        # those lines from the verified source in this same
                        # transaction; account/transaction UUIDs and local
                        # queues remain bound to their existing identities.
                        store.db.execute('PRAGMA defer_foreign_keys=ON')
                        store.db.execute('DELETE FROM ledger_entries')
                    store.adapter.graph.replace_verified(adapter.graph.snapshot())
                else:
                    keep = {transaction["uuid"] for transaction in transactions}
                    for row in store.db.all("SELECT uuid,local_id FROM journal_ids WHERE entity='transactions'"):
                        if row["uuid"] not in keep:
                            store.db.execute("DELETE FROM ledger_entries WHERE transaction_id=?", (row["local_id"],))
                            store.db.execute("DELETE FROM transactions WHERE id=?", (row["local_id"],))
                            store.db.execute("DELETE FROM journal_ids WHERE entity='transactions' AND uuid=?", (row["uuid"],))
            for transaction in transactions:
                party_uuid = transaction["header"]["counterparty_id"]
                parties = []
                if party_uuid:
                    local = db.scalar("SELECT local_id FROM journal_ids WHERE entity='counterparties' AND uuid=?", (party_uuid,))
                    row = db.one("SELECT * FROM counterparties WHERE id=?", (local,))
                    parties.append(dict(uuid=party_uuid, values=adapter._encode(row, PARTY)))
                store.adapter.apply(dict(schema=1, transactions=[transaction], counterparties=parties))
            fault("snapshot_domain")
            tables = ["journal_records", "journal_aliases", "journal_commits", "journal_sources"]
            for table in ('journal_commit_times', 'journal_compacted'):
                if db.has_table(table):
                    from .retention import initialize
                    initialize(store)
                    tables.append(table)
            for table in tables:
                store.db.execute(f"DELETE FROM {table}")
                for row in db.all(f"SELECT * FROM {table}"):
                    columns = list(row.keys())
                    store.db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", tuple(row))
            if store.fingerprint() != body["fingerprint"] or store.cursor() != body["cursor"]:
                raise JournalError("Checkpoint did not converge")
            # Reconcile saved local decisions only from the signed retained stream.
            for row in store.db.all("SELECT wire FROM journal_commits"):
                commit = unpack(bytes(row[0]))["body"]
                own = store.db.one("SELECT wire FROM journal_outbox WHERE proposal_id=?", (commit["proposal_id"],))
                if own:
                    from .retention import proposal_hash
                    if proposal_hash(own[0]) != commit["proposal_hash"]:
                        raise JournalError("Snapshot decision does not match saved proposal")
                    store.db.execute("UPDATE journal_outbox SET decision=? WHERE proposal_id=?", (row[0], commit["proposal_id"]))
            fault("snapshot_cursor")
        fault("snapshot_committed")
    except BaseException:
        if upgrading:
            actual = json.loads(store.db.scalar('SELECT config FROM journal_meta WHERE id=1'))
            if actual['version'] == old_config['version']:
                store.adapter, store.config = old_adapter, old_config
                store.db.conn.set_authorizer(old_adapter._authorize)
                store.db.journal_guard = old_adapter._authorize
        raise
    finally:
        db.close()
        path.unlink(missing_ok=True)
