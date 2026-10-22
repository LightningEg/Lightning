"""Device-bound encrypted backup packages and non-rewinding queue recovery.

This imports saved original proposals into an existing verified device; it never
restores an older home ledger or silently reinstalls an old origin incarnation.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from lightning.database.connection import Database
from lightning.database.snapshot import snapshot, verify_connection
from .codec import JournalError, authenticate, canonical, cursor as validate_cursor, digest, fields, hash_value, number, seal, unpack
from .snapshots import _hash, _stage

_RECOVERED_MAP_DDL = ("CREATE TABLE journal_recovered_originals("
                      "original_id TEXT PRIMARY KEY, original_hash TEXT NOT NULL, new_proposal_id TEXT, "
                      "status TEXT NOT NULL, reason TEXT NOT NULL, decision BLOB)")


def _ensure_recovered_map(store):
    """Install one fixed local recovery table without relaxing financial writes."""
    db = store.db
    obj = db.one("SELECT type FROM sqlite_master WHERE name='journal_recovered_originals'")
    if obj is not None and obj["type"] != "table":
        raise JournalError("The recovered-work map is damaged; preserve this profile for repair")
    if obj is None:
        if db.conn.in_transaction:
            raise JournalError("Finish the current save before recovering a backup")
        # The only operation performed while the financial authorizer is absent
        # is this literal schema statement; all map data and proposals remain
        # behind the normal journal authorizer and database transaction.
        db.conn.set_authorizer(None)
        try:
            with db.transaction():
                db.execute(_RECOVERED_MAP_DDL)
        finally:
            db.conn.set_authorizer(store.adapter._authorize)
    columns = db.all("PRAGMA table_info(journal_recovered_originals)")
    names = {row["name"] for row in columns}
    if (names != {"original_id", "original_hash", "new_proposal_id", "status", "reason", "decision"}
            or sum(row["pk"] == 1 for row in columns) != 1
            or next((row["pk"] for row in columns if row["name"] == "original_id"), 0) != 1):
        raise JournalError("The recovered-work map is damaged; preserve this profile for repair")


def _fsync_directory(folder):
    if os.name != "nt":
        descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


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
    store.adapter.verify()
    fingerprint = store.adapter.fingerprint(full=True)
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
                fingerprint=fingerprint, created_at=datetime.now(timezone.utc).isoformat(),
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


def restore_copy(source, wire, *, backup_key, target, new_device, new_incarnation):
    """Materialize a journal backup as a quarantined, read-only comparison copy.

    The saved database and original proposal identities remain intact. A fresh
    identity is recorded only as an enrollment intent; it is not installed or
    admitted here. The runtime must open this copy read-only until a new
    checkpoint is enrolled and original proposals are explicitly reconciled.
    """
    from .codec import cursor as validate_cursor, hash_value, number, uuid

    target = Path(target)
    if target.is_symlink():
        raise JournalError("The restore target already exists; keep both copies for review")
    if target.parent.is_symlink():
        raise JournalError("The restore folder is unsafe")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    envelope = unpack(wire)
    body = envelope["body"]
    fields(body, ("version", "type", "profile", "generation", "device", "incarnation", "next_seq", "cursor", "fingerprint", "created_at", "size", "sha256"))
    if body["version"] != 2 or body["type"] != "journal-device-backup":
        raise JournalError("Unsupported device backup")
    for key in ("profile", "generation", "device", "incarnation"):
        uuid(body[key])
    uuid(new_device)
    uuid(new_incarnation)
    if new_device == body["device"] or new_incarnation == body["incarnation"]:
        raise JournalError("A restored copy needs a fresh identity and incarnation")
    number(body["next_seq"], minimum=1)
    number(body["size"], minimum=1)
    validate_cursor(body["cursor"])
    hash_value(body["fingerprint"])
    hash_value(body["sha256"])
    staged = _stage(Path(source), target.parent, body["sha256"], body["size"])
    descriptor_path = target.with_name(target.name + ".journal-restore.json")
    try:
        if descriptor_path.is_symlink():
            raise JournalError("Restore descriptor is unsafe; preserve it for repair")
        candidate = Database(staged, key=backup_key, read_only=True)
        try:
            verify_connection(candidate.conn, encrypted=True)
            config = json.loads(candidate.scalar("SELECT config FROM journal_meta WHERE id=1"))
            material = json.loads(candidate.scalar("SELECT document FROM journal_backup_material WHERE id=1") or "{}")
            if (config.get("profile") != body["profile"] or config.get("generation") != body["generation"]
                    or config.get("device") != body["device"] or config.get("incarnation") != body["incarnation"]
                    or candidate.scalar("SELECT next_seq FROM journal_meta WHERE id=1") != body["next_seq"]):
                raise JournalError("Backup identity or counter mismatch")
            if material.get("public_key") is None:
                raise JournalError("Backup identity material is missing")
            authenticate(envelope, material["public_key"])
            from .effects import Replicator
            from .store import JournalStore
            saved = JournalStore(candidate)
            fingerprint = Replicator(candidate, config["profile"]).fingerprint(cached=False)
            if saved.cursor() != body["cursor"] or fingerprint != body["fingerprint"]:
                raise JournalError("Backup manifest does not match its saved ledger state")
        finally:
            candidate.close()
        descriptor = dict(version=1, status="installing", profile=body["profile"],
                          generation=body["generation"], source_device=body["device"],
                          source_incarnation=body["incarnation"], new_device=new_device,
                          new_incarnation=new_incarnation, source_sha256=body["sha256"],
                          preserved_database=target.name)
        if descriptor_path.exists():
            try:
                prior = json.loads(descriptor_path.read_text("utf-8"))
            except (OSError, ValueError) as error:
                raise JournalError("Restore descriptor is damaged; preserve it for repair") from error
            if any(prior.get(key) != value for key, value in descriptor.items() if key != "status") \
                    or prior.get("status") not in ("installing", "requires-enrollment"):
                raise JournalError("Restore descriptor belongs to another operation")
            descriptor = prior
        elif target.exists():
            raise JournalError("The restore target already exists; keep both copies for review")
        else:
            payload = json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
            fd = os.open(descriptor_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(target.parent)
        if target.exists():
            if _hash(target) != body["sha256"]:
                raise JournalError("The interrupted restore target is incomplete or changed; preserve it")
            restored = Database(target, key=backup_key, read_only=True)
            try:
                verify_connection(restored.conn, encrypted=True)
            finally:
                restored.close()
            descriptor["status"] = "requires-enrollment"
            temporary = descriptor_path.with_name(descriptor_path.name + f".{uuid4().hex}.partial")
            with temporary.open("xb") as handle:
                handle.write(json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, descriptor_path)
            _fsync_directory(target.parent)
            return descriptor_path, descriptor
        try:
            target_fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            target_handle = os.fdopen(target_fd, "wb")
            try:
                source_handle = staged.open("rb")
            except BaseException:
                target_handle.close()
                raise
            with source_handle as source_file, target_handle as target_file:
                shutil.copyfileobj(source_file, target_file, 1024 * 1024)
                target_file.flush()
                os.fsync(target_file.fileno())
        except BaseException:
            # The descriptor and any partial file keep the target quarantined;
            # a retry must inspect rather than overwrite these bytes.
            raise
        staged.unlink()
        _fsync_directory(target.parent)
        restored = Database(target, key=backup_key, read_only=True)
        try:
            verify_connection(restored.conn, encrypted=True)
        finally:
            restored.close()
        if _hash(target) != body["sha256"]:
            raise JournalError("Restored comparison copy changed during publication")
        descriptor["status"] = "requires-enrollment"
        temporary = descriptor_path.with_name(descriptor_path.name + f".{uuid4().hex}.partial")
        with temporary.open("xb") as handle:
            handle.write(json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, descriptor_path)
        _fsync_directory(target.parent)
        return descriptor_path, descriptor
    except BaseException:
        # Keep any descriptor/target once installation starts; it is quarantined
        # evidence and must be inspected rather than overwritten on retry.
        staged.unlink(missing_ok=True)
        raise


def repropose_copy(device, source, manifest, *, backup_key):
    """Explicitly re-create pending work from a quarantined backup on a newly enrolled replica.

    Original signed proposals and their old incarnation remain in the restore copy. This writes
    fresh proposals signed by the current device, retaining their original groups and bases. The
    recovery map commits with each new outbox entry, so retry cannot duplicate a proposal.
    """
    from .codec import origin_id, proposal as validate_proposal
    from .store import JournalStore

    store, db = device.store, device.store.db
    if store.config.get("role") != "replica":
        raise JournalError("Recovered work must be enrolled on the current home as a new replica")
    if store.config.get("origin_key") != device.identity.public_key:
        raise JournalError("The enrolled device identity does not match this replica")
    store.verify()
    authority = store.authority
    if authority is None:
        raise JournalError("Pinned authority history is required before recovering original proposals")
    generations = authority.generation_home_keys()
    if generations.get(store.config["generation"]) != store.config["home_key"]:
        raise JournalError("The current replica is outside its pinned authority history")
    from .store import _commit
    receipts = {}
    previous = "0" * 64
    expected_revision = 1
    for receipt_row in db.all("SELECT revision,hash,proposal_id,wire FROM journal_commits ORDER BY revision"):
        receipt_wire = bytes(receipt_row["wire"])
        receipt_envelope = unpack(receipt_wire)
        receipt_body = receipt_envelope["body"]
        home_key = generations.get(receipt_body.get("generation"))
        if home_key is None:
            raise JournalError("A current receipt belongs to an unknown authority generation")
        authenticate(receipt_envelope, home_key)
        _commit(receipt_body)
        if (receipt_body["revision"] != expected_revision or receipt_body["previous"] != previous
                or receipt_body["profile"] != store.config["profile"]
                or receipt_body["proposal_id"] != receipt_row["proposal_id"]
                or digest(receipt_body) != receipt_row["hash"]):
            raise JournalError("The current decision stream is not a verified chain")
        receipts[receipt_row["proposal_id"]] = (receipt_body, receipt_wire)
        previous, expected_revision = receipt_row["hash"], expected_revision + 1
    current = store.cursor()
    if current["revision"] != expected_revision - 1 or current["hash"] != previous:
        raise JournalError("The current decision stream is not a verified chain")
    envelope = unpack(manifest)
    body = envelope["body"]
    fields(body, ("version", "type", "profile", "generation", "device", "incarnation", "next_seq", "cursor", "fingerprint", "created_at", "size", "sha256"))
    if body["version"] != 2 or body["type"] != "journal-device-backup":
        raise JournalError("Unsupported device backup")
    for key in ("profile", "generation", "device", "incarnation"):
        from .codec import uuid
        uuid(body[key])
    number(body["next_seq"], minimum=1)
    number(body["size"], minimum=1)
    validate_cursor(body["cursor"])
    hash_value(body["fingerprint"])
    hash_value(body["sha256"])
    if (body["profile"] != store.config["profile"]
            or not authority.admits_original(dict(profile=body["profile"], generation=body["generation"]))):
        raise JournalError("The backup generation is absent from pinned authority history")
    if body["device"] == store.config["device"] or body["incarnation"] == store.config["incarnation"]:
        raise JournalError("Recovery requires a newly enrolled device and incarnation")

    staged = _stage(Path(source), Path(db.path).parent, body["sha256"], body["size"])
    candidate = Database(staged, key=backup_key, read_only=True)
    try:
        verify_connection(candidate.conn, encrypted=True)
        saved = JournalStore(candidate)
        source_config = saved.config
        if (source_config["profile"] != body["profile"] or source_config["generation"] != body["generation"]
                or source_config["device"] != body["device"] or source_config["incarnation"] != body["incarnation"]
                or candidate.scalar("SELECT next_seq FROM journal_meta WHERE id=1") != body["next_seq"]):
            raise JournalError("Backup identity or counter mismatch")
        if generations.get(source_config["generation"]) != source_config["home_key"]:
            raise JournalError("Backup home key does not match the pinned authority generation")
        material = json.loads(candidate.scalar("SELECT document FROM journal_backup_material WHERE id=1") or "{}")
        old_key = material.get("public_key")
        if material.get("device") != body["device"] or material.get("incarnation") != body["incarnation"] or not old_key:
            raise JournalError("Backup identity material is missing")
        if old_key != source_config["origin_key"]:
            raise JournalError("Backup origin key does not match its saved identity")
        authenticate(envelope, old_key)
        from .effects import Replicator
        if saved.cursor() != body["cursor"] or Replicator(candidate, source_config["profile"]).fingerprint(cached=False) != body["fingerprint"]:
            raise JournalError("Backup manifest does not match its saved checkpoint")
        originals = []
        for row in candidate.all("SELECT seq,proposal_id,wire,decision FROM journal_outbox ORDER BY seq"):
            original_wire = bytes(row["wire"])
            original = unpack(original_wire)
            authenticate(original, old_key)
            validate_proposal(original["body"])
            origin = original["body"]["origin"]
            if (origin != dict(device=body["device"], incarnation=body["incarnation"], seq=row["seq"])
                    or origin_id(origin) != row["proposal_id"]):
                raise JournalError("Backup proposal identity mismatch")
            if row["decision"] is None:
                originals.append((row["proposal_id"], original["body"], original_wire))

        # A current verified checkpoint is required before identifying old receipts.
        _ensure_recovered_map(store)
        counts = {"reproposed": 0, "already_decided": 0, "held": 0}
        with db.transaction():
            for original_id, original, _wire in originals:
                original_hash = digest(original)
                saved_map = db.one("SELECT original_hash,new_proposal_id,status FROM journal_recovered_originals WHERE original_id=?",
                                   (original_id,))
                if saved_map:
                    if saved_map["original_hash"] != original_hash:
                        raise JournalError("A recovered original identity has changed; preserve both copies")
                    if saved_map["status"] not in {"reproposed", "already_decided", "held"}:
                        raise JournalError("The recovered-work map is damaged; preserve this profile for repair")
                    if saved_map["status"] == "reproposed":
                        new = db.one("SELECT wire FROM journal_outbox WHERE proposal_id=?", (saved_map["new_proposal_id"],))
                        if new is None:
                            raise JournalError("A recovered proposal is missing; preserve the profile for repair")
                        new_envelope = unpack(bytes(new["wire"]))
                        authenticate(new_envelope, device.identity.public_key)
                        validate_proposal(new_envelope["body"])
                        if origin_id(new_envelope["body"]["origin"]) != saved_map["new_proposal_id"]:
                            raise JournalError("A recovered proposal identity changed; preserve the profile for repair")
                    counts[saved_map["status"]] += 1
                    continue

                receipt_value = receipts.get(original_id)
                if receipt_value is not None:
                    result, receipt_wire = receipt_value
                    if result["proposal_hash"] != original_hash:
                        raise JournalError("A saved receipt disagrees with the backed-up proposal")
                    db.execute("INSERT INTO journal_recovered_originals VALUES(?,?,?,?,?,?)",
                               (original_id, original_hash, None, "already_decided", result["outcome"], bytes(receipt_wire)))
                    counts["already_decided"] += 1
                    continue

                dependencies = []
                bases = dict(original["bases"])
                held_reason = ""
                for dependency in original["dependencies"]:
                    dep_id = origin_id(dependency)
                    dep = db.one("SELECT original_hash,new_proposal_id,status,reason FROM journal_recovered_originals WHERE original_id=?",
                                 (dep_id,))
                    dep_receipt = receipts.get(dep_id)
                    if dep_receipt is not None:
                        dep_body, _ = dep_receipt
                        if dep_body["outcome"] == "rejected":
                            held_reason = "dependency-rejected"
                            break
                        if dep_body["outcome"] in ("accepted", "accepted-as-existing"):
                            for effect in dep_body["effects"]:
                                for group, token in effect["tokens"].items():
                                    if bases.get(group) is None:
                                        bases[group] = token
                            continue
                    if dep is None:
                        held_reason = "dependency-unresolved"
                        break
                    if dep["status"] == "held":
                        held_reason = "dependency-held"
                        break
                    if dep["status"] == "already_decided":
                        if dep["reason"] == "rejected":
                            held_reason = "dependency-rejected"
                            break
                        continue
                    if dep["status"] != "reproposed":
                        held_reason = "dependency-unresolved"
                        break
                    parent_wire = db.scalar("SELECT wire FROM journal_outbox WHERE proposal_id=?", (dep["new_proposal_id"],))
                    if parent_wire is None:
                        raise JournalError("A recovered parent proposal is missing; preserve the profile for repair")
                    dependencies.append(unpack(bytes(parent_wire))["body"]["origin"])

                if held_reason:
                    db.execute("INSERT INTO journal_recovered_originals VALUES(?,?,?,?,?,NULL)",
                               (original_id, original_hash, None, "held", held_reason))
                    counts["held"] += 1
                    continue

                # Preserve the original causal bases and groups. Only bases that were
                # deliberately absent because an already-confirmed parent produced them
                # are replaced with that exact receipt's resulting field tokens.
                new_wire = store.save(kind=original["kind"], record=original["record"], groups=original["groups"],
                    bases=bases, signer=device.identity.sign, dependencies=dependencies,
                    display_zone=original["display_zone"])
                new_id = origin_id(unpack(new_wire)["body"]["origin"])
                db.execute("INSERT INTO journal_recovered_originals VALUES(?,?,?,?,?,NULL)",
                           (original_id, original_hash, new_id, "reproposed", ""))
                counts["reproposed"] += 1
        return counts
    finally:
        candidate.close()
        staged.unlink(missing_ok=True)
