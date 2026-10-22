"""Durable opaque mailbox transport, using the same signed encrypted local wire.

No data key is sent to the service. Queued requests/replies survive restarts;
network acknowledgement follows an encrypted local receipt, never a download.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .codec import JournalError, authenticate, canonical, digest, fields, unpack

CHUNK_SIZE = 32768
MAX_SNAPSHOT = 200 * 1024 * 1024
REFUSED = 2  # journal_mail_in.processed: opened or answered with a refusal, acknowledged, never retried


def raw_signature(identity, body):
    """WebCrypto uses IEEE P1363; the existing device signer returns DER."""
    r, s = decode_dss_signature(bytes.fromhex(identity.sign(canonical(body))))
    return (r.to_bytes(32, "big") + s.to_bytes(32, "big")).hex()


class CloudUnavailable(JournalError):
    """Transient carrier failure. The caller retains every durable source."""


class ReplyPending(CloudUnavailable):
    """The carrier works; the home has not answered yet. This is waiting, not failure."""


class HomeRefused(CloudUnavailable):
    """The home answered that it cannot take this request now (frozen, full); retry later."""


class MailboxClient:
    def __init__(self, base_url, device):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise JournalError("Use the configured HTTPS mailbox origin")
        self.base = base_url.rstrip("/")
        self.device = device

    async def call(self, route, payload=None):
        if not route.startswith("/") or "?" in route:
            raise JournalError("Invalid mailbox operation")
        data = canonical(payload or {})
        if len(data) > 96 * 1024:
            raise JournalError("Mailbox request size limit exceeded")
        config = self.device.store.config
        path = f'/profiles/{config["profile"]}{route}'
        body = dict(device=config["device"], profile=config["profile"], generation=config["generation"],
                    method="POST", path=path, time=int(time.time() * 1000), nonce=secrets.token_hex(32),
                    sha256=hashlib.sha256(data).hexdigest())
        auth = json.dumps(dict(body=body, signature=raw_signature(self.device.identity, body)), separators=(",", ":"))
        return await asyncio.to_thread(self._send, path, data, auth)

    def _send(self, path, data, auth):
        request = Request(self.base + path, data=data, method="POST", headers={
            "Content-Type": "application/json", "X-Journal-Auth": auth})
        try:
            # Default TLS verification and inherited proxy/CA configuration.
            with urlopen(request, timeout=10) as response:
                wire = response.read(128 * 1024 + 1)
            if len(wire) > 128 * 1024:
                raise JournalError("Mailbox response size limit exceeded")
            return json.loads(wire)
        except HTTPError as error:
            if error.code == 409:
                raise CloudUnavailable("Authority or checkpoint changed; verify before continuing") from None
            if error.code in (401, 403):
                raise JournalError("The mailbox refused this device; check its membership") from None
            raise CloudUnavailable("Mailbox unavailable or quota reached; edits remain on this device") from None
        except (OSError, TimeoutError, ValueError) as error:
            raise CloudUnavailable("Mailbox unavailable; edits remain on this device") from error


def install(store):
    """Add local transport state inside the encrypted laboratory profile only."""
    tables = (
        "CREATE TABLE IF NOT EXISTS journal_mail_in(id TEXT PRIMARY KEY,sender TEXT NOT NULL,wire BLOB NOT NULL,processed INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS journal_mail_out(id TEXT PRIMARY KEY,recipient TEXT NOT NULL,wire BLOB NOT NULL)",
        "CREATE TABLE IF NOT EXISTS journal_rpc(id TEXT PRIMARY KEY,wire BLOB NOT NULL,response BLOB,consumed INTEGER NOT NULL DEFAULT 0)",
    )
    # Fixed local-only DDL on the owning thread; no callbacks/network can run
    # while canonical protection is temporarily lifted for sqlite_master.
    store.db.conn.set_authorizer(None)
    try:
        with store.db.transaction():
            for statement in tables:
                store.db.execute(statement)
    finally:
        if store.adapter is not None:
            store.db.conn.set_authorizer(store.adapter._authorize)



class MailboxPeer:
    def __init__(self, channel, client):
        self.channel, self.client = channel, client
        self.store, self.db = channel.device.store, channel.device.store.db
        install(self.store)

    def enqueue(self, wire):
        envelope = unpack(wire)["body"]
        self.store._scope(envelope)
        if envelope["sender"] != self.store.config["device"]:
            raise JournalError("Cannot upload another device's routing envelope")
        identifier = hashlib.sha256(wire).hexdigest()
        self.db.execute("INSERT OR IGNORE INTO journal_mail_out VALUES(?,?,?)", (identifier, envelope["recipient"], wire))
        return identifier

    async def pump(self, *, budget=20, fault=lambda phase: None):
        """Bound work per wake-up; no sleeping while holding an open transaction."""
        from .local import MembershipUpdateRequired
        if type(budget) is not int or not 1 <= budget <= 50:
            raise JournalError("Invalid background work budget")
        for row in self.db.all("SELECT * FROM journal_mail_out ORDER BY rowid LIMIT ?", (budget,)):
            await self.client.call("/send", dict(id=row["id"], recipient=row["recipient"], wire=base64.b64encode(row["wire"]).decode("ascii")))
            # The RPC or committed financial source still owns retransmission after
            # mailbox expiry; a send acknowledgement is never a financial decision.
            with self.db.transaction():
                self.db.execute("DELETE FROM journal_mail_out WHERE id=?", (row["id"],))
        response = await self.client.call("/receive")
        if type(response) is not dict or type(response.get("messages")) is not list or len(response["messages"]) > 20:
            raise JournalError("Invalid mailbox delivery")
        acknowledgements = []
        for message in response["messages"][:budget]:
            fields(message, ("id", "sender", "wire"))
            if type(message["wire"]) is not str or len(message["wire"]) > 87500:
                raise JournalError("Oversized mailbox delivery")
            try:
                wire = base64.b64decode(message["wire"], validate=True)
            except ValueError as error:
                raise JournalError("Invalid mailbox encoding") from error
            if hashlib.sha256(wire).hexdigest() != message["id"]:
                raise JournalError("Invalid mailbox content digest")
            from .local import MembershipUpdateRequired
            obsolete = False
            try:
                sender, _ = self.channel.open(wire)
            except MembershipUpdateRequired:
                # The outer paired signature was authenticated before this
                # exception. The sender retains its original financial source
                # and retries it under the independently fetched new key epoch.
                sender = unpack(wire)["body"]["sender"]
                obsolete = True
            except JournalError:
                # An envelope that cannot be opened must not block those behind it:
                # keep it as refused (processed=2), then acknowledge it with the rest.
                sender, obsolete = message["sender"], REFUSED
            if sender != message["sender"]:
                raise JournalError("Mailbox sender mismatch")
            with self.db.transaction():
                self.db.execute("INSERT OR IGNORE INTO journal_mail_in(id,sender,wire,processed) VALUES(?,?,?,?)", (message["id"], sender, wire,int(obsolete)))
            fault("delivery_durable")
            acknowledgements.append(dict(id=message["id"], sender=sender))
        if acknowledgements:
            await self.client.call("/ack", dict(messages=acknowledgements))
        fault("delivery_acknowledged")
        # Durable incoming rows remain available even if processing fails.
        for row in self.db.all("SELECT * FROM journal_mail_in WHERE processed=0 ORDER BY rowid LIMIT ?", (budget,)):
            wire = bytes(row["wire"])
            try:
                with self.db.transaction():
                    if self.channel.device.home:
                        try:
                            answer = self.channel.handle(wire)
                        except MembershipUpdateRequired:
                            self.db.execute("UPDATE journal_mail_in SET processed=1 WHERE id=?",(row["id"],))
                            continue
                        except JournalError as error:
                            answer = self.channel.refusal(wire, error)
                        self.enqueue(answer)
                    else:
                        try:
                            _, payload = self.channel.open(wire)
                        except MembershipUpdateRequired:
                            self.db.execute("UPDATE journal_mail_in SET processed=1 WHERE id=?", (row["id"],))
                            continue
                        fields(payload, ("request_nonce", "result"))
                        pending = self.db.all("SELECT id,wire FROM journal_rpc WHERE response IS NULL")
                        request = next((item for item in pending if unpack(bytes(item["wire"]))["body"]["nonce"] == payload["request_nonce"]), None)
                        if request is None:
                            self.db.execute("UPDATE journal_mail_in SET processed=1 WHERE id=?", (row["id"],))
                            continue  # An authenticated delayed reply to an already consumed RPC.
                        self.db.execute("UPDATE journal_rpc SET response=? WHERE id=?", (wire, request["id"]))
                    self.db.execute("UPDATE journal_mail_in SET processed=1 WHERE id=?", (row["id"],))
            except JournalError:
                with self.db.transaction():
                    self.db.execute("UPDATE journal_mail_in SET processed=? WHERE id=?", (REFUSED, row["id"]))
            fault("delivery_processed")


class MailboxExchange:
    """Restartable RPC for LocalChannel; an offline home never loses the request."""
    def __init__(self, peer):
        self.peer, self.db = peer, peer.db

    def prepare(self, payload, recipient):
        identifier = digest(dict(payload=payload, recipient=recipient, generation=self.peer.store.config["generation"],epoch=self.peer.channel.epoch))
        row = self.db.one("SELECT wire,consumed FROM journal_rpc WHERE id=?", (identifier,))
        # Capabilities and immutable proposal delivery are stable for this
        # payload/key epoch. Reuse them across interrupted rounds, otherwise
        # each wake restarts at capabilities and starves later RPC stages.
        # Status and changes must refresh after consumption to see new work.
        if row and (not row["consumed"] or payload["operation"] in {"capabilities", "proposal"}):
            return bytes(row["wire"])
        wire = self.peer.channel.protect(payload, recipient)
        with self.db.transaction():
            self.db.execute("INSERT OR REPLACE INTO journal_rpc VALUES(?,?,NULL,0)", (identifier, wire))
        return wire

    async def __call__(self, wire):
        row = self.db.one("SELECT response FROM journal_rpc WHERE wire=?", (wire,))
        if row is None:
            raise JournalError("Persist the mailbox request before sending")
        if row["response"] is not None:
            with self.db.transaction():
                self.db.execute("UPDATE journal_rpc SET consumed=1 WHERE wire=?", (wire,))
            return bytes(row["response"])
        with self.db.transaction():
            self.peer.enqueue(wire)
        await self.peer.pump()
        row = self.db.one("SELECT response FROM journal_rpc WHERE wire=?", (wire,))
        if row["response"] is None:
            raise ReplyPending("Queued for the home; this edit remains pending")
        with self.db.transaction():
            self.db.execute("UPDATE journal_rpc SET consumed=1 WHERE wire=?", (wire,))
        return bytes(row["response"])


class CheckpointTransfer:
    """Resumable ciphertext-only chunks; the signed manifest binds final bytes."""
    def __init__(self, client, folder):
        self.client, self.folder = client, Path(folder)
        if self.folder.is_symlink():
            raise JournalError("Invalid checkpoint cache directory")
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)

    @staticmethod
    def manifest(wire, public_key):
        envelope = unpack(wire)
        authenticate(envelope, public_key)
        body = envelope["body"]
        fields(body, ("version", "type", "profile", "generation", "cursor", "fingerprint", "catalog", "schema", "size", "sha256"))
        if body["type"] != "snapshot" or body["version"] != 2 or type(body["size"]) is not int or not 0 < body["size"] <= MAX_SNAPSHOT:
            raise JournalError("Unsupported checkpoint manifest")
        from .codec import hash_value
        hash_value(body["sha256"])
        return body

    async def upload(self, source, wire, *, recipient, public_key, budget=50):
        manifest = self.manifest(wire, public_key)
        source = Path(source)
        if source.is_symlink() or source.stat().st_size != manifest["size"]:
            raise JournalError("Checkpoint file size mismatch")
        identifier = hashlib.sha256(wire).hexdigest()
        await self.client.call("/snapshot/start", dict(id=identifier, recipient=recipient, size=manifest["size"], sha256=manifest["sha256"], manifest=wire.decode("utf-8")))
        status = await self.client.call("/snapshot/status", dict(id=identifier))
        completed = set(status["chunks"])
        sent = 0
        with source.open("rb") as handle:
            for index in range((manifest["size"] + CHUNK_SIZE - 1) // CHUNK_SIZE):
                if index in completed:
                    continue
                if sent >= budget:
                    return dict(id=identifier, complete=False)
                handle.seek(index * CHUNK_SIZE)
                data = handle.read(CHUNK_SIZE)
                await self.client.call("/snapshot/put", dict(id=identifier, index=index, bytes=base64.b64encode(data).decode("ascii"), sha256=hashlib.sha256(data).hexdigest()))
                sent += 1
        await self.client.call("/snapshot/finish", dict(id=identifier))
        return dict(id=identifier, complete=True)

    async def download(self, wire, *, public_key, budget=50):
        manifest = self.manifest(wire, public_key)
        identifier = hashlib.sha256(wire).hexdigest()
        target = self.folder / f"{identifier}.db"
        chunks = (manifest["size"] + CHUNK_SIZE - 1) // CHUNK_SIZE
        received = 0
        for index in range(chunks):
            part = self.folder / f"{identifier}.{index}.chunk"
            # Each part has a local digest sidecar. A corrupted/interrupted local
            # write is redownloaded; the signed whole hash remains authoritative.
            checksum = part.with_suffix(".hash")
            expected_size = min(CHUNK_SIZE, manifest["size"] - index * CHUNK_SIZE)
            if (part.is_file() and not part.is_symlink() and part.stat().st_size == expected_size
                    and checksum.is_file() and not checksum.is_symlink() and checksum.stat().st_size == 64):
                data = part.read_bytes()
                if len(data) == expected_size and hashlib.sha256(data).hexdigest() == checksum.read_text():
                    continue
            if received >= budget:
                return None
            response = await self.client.call("/snapshot/get", dict(id=identifier, index=index))
            encoded = response.get("bytes")
            if type(encoded) is not str or len(encoded) > 44000:
                raise JournalError("Invalid checkpoint chunk")
            try:
                data = base64.b64decode(encoded, validate=True)
            except ValueError as error:
                raise JournalError("Invalid checkpoint chunk") from error
            if len(data) != expected_size or hashlib.sha256(data).hexdigest() != response.get("sha256"):
                raise JournalError("Checkpoint chunk hash mismatch")
            # Snapshot bytes are already SQLCipher ciphertext; no plaintext spool.
            self._write(part, data)
            self._write(checksum, response["sha256"].encode("ascii"))
            received += 1
        total = hashlib.sha256()
        temporary = target.with_suffix(".assembling")
        try:
            with temporary.open("wb") as handle:
                for index in range(chunks):
                    data = (self.folder / f"{identifier}.{index}.chunk").read_bytes()
                    total.update(data)
                    handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if total.hexdigest() != manifest["sha256"]:
                raise JournalError("Checkpoint file hash mismatch; preserve current ledger")
            os.replace(temporary, target)
            return target
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _write(path, data):
        temporary = path.with_suffix(path.suffix + ".arriving")
        if path.is_symlink() or temporary.is_symlink():
            raise JournalError("Invalid checkpoint cache path")
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)


class RetryWindow:
    """Bounded exponential backoff; push is only a wake-up hint."""
    def __init__(self, *, clock=time.monotonic, jitter=secrets.randbelow):
        self.clock, self.jitter = clock, jitter
        self.failures, self.next_attempt = 0, 0

    def ready(self):
        return self.clock() >= self.next_attempt

    def waiting(self, delay=30):
        """The carrier answered and the home is simply not done: a short fixed wait, no backoff."""
        self.failures = 0
        self.next_attempt = self.clock() + delay + self.jitter(max(1, delay // 4))

    def result(self, success):
        self.failures = 0 if success else min(self.failures + 1, 10)
        delay = 30 if success else min(3600, 5 * 2 ** self.failures)
        self.next_attempt = self.clock() + delay + self.jitter(max(1, delay // 4))
