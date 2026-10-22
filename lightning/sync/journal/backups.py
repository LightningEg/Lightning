"""Device-bound encrypted backup packages and non-rewinding queue recovery.

This imports saved original proposals into an existing verified device; it never
restores an older home ledger or silently reinstalls an old origin incarnation.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from lightning.database.connection import Database
from lightning.database.snapshot import snapshot, verify_connection
from .codec import JournalError, authenticate, canonical, cursor as validate_cursor, digest, fields, hash_value, number, seal, unpack
from .snapshots import _hash, _stage


def create(device, target, *, key_document, owner_document=None):
    """Caller owns the profile/session lock; no network or concurrent save here."""
    store, db = device.store, device.store.db
    target = Path(target)
    if not db.encrypted:
        raise JournalError("Backups require an encrypted profile")
    from lightning.security.keys import key_id
    if key_document.get("key_id") != key_id(db.copy_key()):
        raise JournalError("Backup key material belongs to another profile")
    if owner_document is not None and owner_document.get("profile") != store.config["profile"]:
        raise JournalError("Backup owner authority belongs to another profile")
    db.conn.set_authorizer(None)
    try:
        snapshot(db, target)
    finally:
        if store.adapter:
            db.conn.set_authorizer(store.adapter._authorize)
    saved = Database(target, key=db.copy_key())
    try:
        with saved.transaction():
            saved.execute("CREATE TABLE IF NOT EXISTS journal_backup_material(id INTEGER PRIMARY KEY CHECK(id=1),document TEXT NOT NULL)")
            material = dict(device=device.identity.device_id, incarnation=store.config["incarnation"],
                            public_key=device.identity.public_key, name=device.identity.name,
                            private_key=device.identity.key_path.read_text(), certificate=device.identity.cert_path.read_text(),
                            keys=key_document, owner=owner_document)
            saved.execute("INSERT OR REPLACE INTO journal_backup_material VALUES(1,?)", (json.dumps(material, separators=(",", ":")),))
        verify_connection(saved.conn, encrypted=True)
    finally:
        saved.close()
    body = dict(version=2, type="journal-device-backup", profile=store.config["profile"], generation=store.config["generation"],
                device=store.config["device"], incarnation=store.config["incarnation"],
                next_seq=db.scalar("SELECT next_seq FROM journal_meta WHERE id=1"), cursor=store.cursor(),
                fingerprint=store.fingerprint(), created_at=datetime.now(timezone.utc).isoformat(),
                size=target.stat().st_size, sha256=_hash(target))
    return seal(body, device.identity.sign)


def recover_queue(device, source, wire, *, backup_key, fault=lambda phase: None):
    store, db = device.store, device.store.db
    envelope = unpack(wire)
    authenticate(envelope, device.identity.public_key)
    body = envelope["body"]
    fields(body, ("version", "type", "profile", "generation", "device", "incarnation", "next_seq", "cursor", "fingerprint", "created_at", "size", "sha256"))
    if body["version"] != 2 or body["type"] != "journal-device-backup":
        raise JournalError("Unsupported device backup")
    number(body["next_seq"], minimum=1)
    number(body["size"], minimum=1)
    validate_cursor(body["cursor"])
    hash_value(body["fingerprint"])
    hash_value(body["sha256"])
    if any(body[key] != store.config[key] for key in ("profile", "generation", "device", "incarnation")):
        raise JournalError("Use explicit recovery/re-pairing for another authority or device incarnation")
    source = _stage(Path(source), Path(db.path).parent, body["sha256"], body["size"])
    candidate = Database(source, key=backup_key, read_only=True)
    try:
        verify_connection(candidate.conn, encrypted=True)
        config = json.loads(candidate.scalar("SELECT config FROM journal_meta WHERE id=1"))
        if config != store.config or candidate.scalar("SELECT next_seq FROM journal_meta WHERE id=1") != body["next_seq"]:
            raise JournalError("Backup identity or counter mismatch")
        from .store import JournalStore
        saved_store = JournalStore(candidate)  # Enforces contiguous original identity slots.
        from .effects import Replicator
        fingerprint = Replicator(candidate, config["profile"]).fingerprint(cached=False)
        if saved_store.cursor() != body["cursor"] or fingerprint != body["fingerprint"]:
            raise JournalError("Backup manifest does not match its saved ledger state")
        material = json.loads(candidate.scalar("SELECT document FROM journal_backup_material WHERE id=1") or "{}")
        if material.get("public_key") != device.identity.public_key or material.get("incarnation") != config["incarnation"]:
            raise JournalError("Backup identity material mismatch")
        incoming = candidate.all("SELECT seq,proposal_id,wire FROM journal_outbox ORDER BY seq")
        # Retain current encrypted evidence before merging the original outbox.
        evidence = Path(db.path).parent / f".before-journal-queue-recovery-{uuid4().hex}.db"
        db.conn.set_authorizer(None)
        try:
            snapshot(db, evidence)
        finally:
            if store.adapter:
                db.conn.set_authorizer(store.adapter._authorize)
        count = 0
        with db.transaction():
            next_seq = db.scalar("SELECT next_seq FROM journal_meta WHERE id=1")
            for row in incoming:
                original = bytes(row["wire"])
                proposal = unpack(original)
                authenticate(proposal, device.identity.public_key)
                from .codec import origin_id, proposal as validate_proposal
                validate_proposal(proposal["body"])
                expected = dict(device=config["device"], incarnation=config["incarnation"], seq=row["seq"])
                if proposal["body"]["origin"] != expected or origin_id(expected) != row["proposal_id"]:
                    raise JournalError("Backup proposal identity mismatch")
                existing = db.one("SELECT wire,proposal_id FROM journal_outbox WHERE seq=?", (row["seq"],))
                if existing:
                    if bytes(existing["wire"]) != original or existing["proposal_id"] != row["proposal_id"]:
                        raise JournalError("Origin identity collision; preserve both copies for review")
                    continue
                if row["seq"] > next_seq:
                    raise JournalError("Backup has an uncertain origin gap; explicit repair required")
                # Never import an old branch's decision over the current stream.
                decision = db.scalar("SELECT wire FROM journal_commits WHERE proposal_id=?", (row["proposal_id"],))
                if decision is not None and unpack(bytes(decision))["body"]["proposal_hash"] != digest(proposal["body"]):
                    raise JournalError("Backup proposal disagrees with the current receipt")
                db.execute("INSERT INTO journal_outbox(seq,proposal_id,wire,decision) VALUES(?,?,?,?)",
                           (row["seq"], row["proposal_id"], original, decision))
                next_seq = max(next_seq, row["seq"] + 1)
                count += 1
            fault("queue_imported")
            if db.scalar("SELECT COUNT(*) FROM journal_outbox") != next_seq - 1:
                raise JournalError("A missing origin slot is not present in this backup")
            db.execute("UPDATE journal_meta SET next_seq=? WHERE id=1", (next_seq,))
            # Unsaved capture remains local work too. Duplicate source identities
            # use the current candidate; a signed saved proposal stays immutable.
            for row in candidate.all("SELECT * FROM journal_candidates"):
                known = db.one("SELECT id FROM journal_candidates WHERE namespace=? AND source_id=?", (row["namespace"], row["source_id"]))
                if known:
                    continue
                columns = list(row.keys())
                db.execute(f"INSERT INTO journal_candidates({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", tuple(row))
                payload = candidate.scalar("SELECT payload_hash FROM journal_candidate_inputs WHERE id=?", (row["id"],))
                db.execute("INSERT INTO journal_candidate_inputs VALUES(?,?)", (row["id"], payload))
            fault("queue_counter")
        fault("queue_recovered")
        return count
    finally:
        candidate.close()
        source.unlink(missing_ok=True)
