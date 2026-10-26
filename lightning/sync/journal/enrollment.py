"""Approved first-replica checkpoints, with no sender-local queues or keys.

The native picker owns directory publication. This module only creates a new
encrypted replica at an explicitly unused path after full verification.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

from lightning.database.connection import Database
from lightning.database.migrator import inspect_schema
from lightning.database.snapshot import verify_connection

from .cloud import CHUNK_SIZE, CheckpointTransfer
from .codec import JournalError, ZERO_HASH, authenticate, canonical, digest, fields, number, seal, unpack, uuid
from .finance import CashAdapter
from .local import encode
from .membership import Membership
from .snapshots import _stage, catalog, export
from .store import JournalStore


class EnrollmentSource:
    def __init__(self, device, *, key_document, approval, owner_document=None):
        self.device, self.keys, self.approval, self.owner = device, key_document, approval, owner_document

    def exchange(self, wire):
        if len(wire) > 4096:
            raise JournalError("Enrollment request limit exceeded")
        envelope = unpack(wire)
        body = envelope["body"]
        fields(body,("type","profile","generation","sender","request","operation","index","nonce"))
        store = self.device.store
        store.require_confirmation_authority()
        store._scope(body)
        from .codec import hash_value
        hash_value(body["request"]); hash_value(body["nonce"])
        saved = self.approval(body["request"])
        if not saved:
            raise JournalError("Enrollment has not been approved")
        from .pairing import approval_receipt
        original = approval_receipt(self.device,saved)
        authenticate(envelope,original["key"])
        if body["type"] != "journal-enrollment" or body["sender"] != original["device"]:
            raise JournalError("Enrollment belongs to another device")
        current = Membership(self.device).state()["members"].get(body["sender"])
        if current != dict(key=original["key"],incarnation=original["incarnation"]):
            raise JournalError("Enrollment device is no longer approved")
        if body["operation"] not in ("metadata","chunk","authority"):
            raise JournalError("Unknown enrollment operation")
        number(body["index"],minimum=0)
        if body["operation"] == "authority":
            if store.authority is None:
                raise JournalError("Authority history is unavailable")
            rows = store.authority.db.execute("SELECT wire FROM certificates WHERE version>? ORDER BY version LIMIT 8",(body["index"],)).fetchall()
            result = dict(certificates=[bytes(row[0]).decode() for row in rows],latest=store.authority.state()["version"])
            return seal(dict(type="journal-enrollment-reply",nonce=body["nonce"],request=body["request"],result=result),self.device.identity.sign)
        folder = Path(store.db.path).parent / ".journal-enrollment"
        if folder.is_symlink():
            raise JournalError("Invalid enrollment cache")
        folder.mkdir(mode=0o700,exist_ok=True)
        path = folder / (body["request"] + ".db")
        cache = store.db.scalar("SELECT value FROM journal_local WHERE name=?",("enrollment:"+body["request"],))
        if cache is None:
            # A previous process may have stopped after exporting but before
            # recording its manifest. Never serve that unbound orphan.
            path.unlink(missing_ok=True)
            existing = list(folder.glob("*.db"))
            if len(existing) > 16:
                raise JournalError("Enrollment cache needs explicit cleanup")
            for old in existing:
                approval = self.approval(old.stem)
                if approval and approval["expires"] <= time.time() and not old.is_symlink():
                    old.unlink()
                    store.db.execute("DELETE FROM journal_local WHERE name=?",("enrollment:"+old.stem,))
            if sum(old.stat().st_size for old in folder.glob("*.db")) + Path(store.db.path).stat().st_size > 400*1024*1024:
                raise JournalError("Enrollment checkpoint cache is full; older transfer windows must expire")
            try:
                manifest = export(store,path,self.device.identity.sign)
                if sum(old.stat().st_size for old in folder.glob("*.db")) > 400*1024*1024:
                    raise JournalError("Enrollment checkpoint cache limit exceeded")
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            store.db.execute("INSERT INTO journal_local VALUES(?,?)",("enrollment:"+body["request"],manifest.decode()))
        else:
            manifest = cache.encode()
        metadata = CheckpointTransfer.manifest(manifest,store.config["home_key"])
        if path.is_symlink() or not path.is_file() or path.stat().st_size != metadata["size"]:
            raise JournalError("Enrollment checkpoint is missing; reopen pairing")
        if body["operation"] == "metadata":
            owner = self.owner() if self.owner is not None else None
            if store.authority is not None and owner is None:
                raise JournalError("Owner recovery material must accompany an enrolled profile")
            result = dict(manifest=manifest.decode(),membership=saved["membership"],keys=self.keys(),owner=owner,
                          authority_version=store.authority.state()["version"] if store.authority else 0)
        else:
            if body["index"] >= (metadata["size"]+CHUNK_SIZE-1)//CHUNK_SIZE:
                raise JournalError("Invalid enrollment chunk")
            with path.open("rb") as handle:
                handle.seek(body["index"]*CHUNK_SIZE)
                data = handle.read(CHUNK_SIZE)
            result = dict(index=body["index"],data=encode(data),sha256=hashlib.sha256(data).hexdigest())
        return seal(dict(type="journal-enrollment-reply",nonce=body["nonce"],request=body["request"],result=result),self.device.identity.sign)


def install_replica(source, manifest, *, key, identity, incarnation, membership, home_key, profile, generation, target, resume=False):
    """Verify signed ciphertext and domain state before publishing a new file."""
    target = Path(target)
    exists = os.path.lexists(target)
    if exists and (not resume or target.is_symlink()):
        raise JournalError("Enrollment never replaces an existing profile")
    for value in (incarnation,profile,generation):
        uuid(value)
    metadata = CheckpointTransfer.manifest(manifest,home_key)
    if metadata["profile"] != profile or metadata["generation"] != generation:
        raise JournalError("Enrollment belongs to another profile or authority")
    if exists:
        saved = Database(target,key=key,read_only=True)
        try:
            verify_connection(saved.conn,encrypted=True)
            store = JournalStore(saved)
            expected = dict(version=2,profile=profile,generation=generation,device=identity.device_id,
                            incarnation=incarnation,home_key=home_key,origin_key=identity.public_key,role="replica")
            adapter = CashAdapter.__new__(CashAdapter)
            adapter.db,adapter.store = saved,store
            if (store.config != expected or store.cursor() != metadata["cursor"] or adapter.fingerprint() != metadata["fingerprint"]
                    or saved.scalar("SELECT next_seq FROM journal_meta") != 1 or saved.scalar("SELECT COUNT(*) FROM journal_outbox")):
                raise JournalError("Existing file differs from the pending enrollment")
            document = unpack(membership)
            authenticate(document,home_key)
            actual = Membership(SimpleNamespace(store=store,identity=identity)).state()
            if any(actual[name] != document["body"][name] for name in ("version","epoch","members","retired")):
                raise JournalError("Existing membership differs from the pending enrollment")
            return target
        finally:
            saved.close()
    staged = _stage(Path(source),target.parent,metadata["sha256"],metadata["size"])
    db = None
    try:
        db = Database(staged,key=key)
        verify_connection(db.conn,encrypted=True)
        inspection = inspect_schema(db)
        if inspection.pending or inspection.current_version != metadata["schema"]:
            raise JournalError("Enrollment needs a compatible application version")
        config = json.loads(db.scalar("SELECT config FROM journal_meta WHERE id=1"))
        if config["role"] != "snapshot" or config["profile"] != profile or config["generation"] != generation:
            raise JournalError("Enrollment checkpoint scope mismatch")
        for table in ("journal_local","journal_outbox","journal_candidates","journal_seen","journal_remote_states",
                      "journal_capture_cursor","journal_batch_undo","journal_drafts","journal_candidate_inputs",
                      "journal_mail_in","journal_mail_out","journal_rpc","journal_backup_material"):
            if db.has_table(table) and db.scalar(f"SELECT COUNT(*) FROM {table}"):
                raise JournalError("Enrollment checkpoint contains sender-local material")
        adapter = CashAdapter.__new__(CashAdapter)
        adapter.db,adapter.store = db,SimpleNamespace(config=config,resolve=lambda value:value)
        if adapter.fingerprint() != metadata["fingerprint"] or catalog(adapter) != metadata["catalog"]:
            raise JournalError("Enrollment financial fingerprint mismatch")
        latest = db.one("SELECT revision,hash FROM journal_commits ORDER BY revision DESC LIMIT 1")
        if (dict(latest) if latest else dict(revision=0,hash=ZERO_HASH)) != metadata["cursor"]:
            raise JournalError("Enrollment cursor mismatch")
        with db.transaction():
            config = dict(version=2,profile=profile,generation=generation,device=identity.device_id,
                          incarnation=incarnation,home_key=home_key,origin_key=identity.public_key,role="replica")
            db.execute("UPDATE journal_meta SET config=?,next_seq=1 WHERE id=1",(canonical(config).decode(),))
            store = JournalStore(db)
            Membership(SimpleNamespace(store=store,identity=identity)).accept(membership,initial=True)
        verify_connection(db.conn,encrypted=True)
        db.close()
        db = None
        with staged.open("rb") as handle:
            os.fsync(handle.fileno())
        try:
            os.link(staged,target)
        except PermissionError:
            if os.path.lexists(target):
                raise FileExistsError(target) from None
            os.rename(staged,target)
        if os.name != "nt":
            descriptor = os.open(target.parent,os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return target
    finally:
        if db is not None:
            db.close()
        staged.unlink(missing_ok=True)
