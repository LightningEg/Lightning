"""Authenticated encrypted local delta messages over the existing pinned TLS link.

Enrollment supplies approved public keys and an independent random transport key.
This module does not pair devices, move authority, or elect a home on timeout.
"""
from __future__ import annotations

import base64
import json
import os
import asyncio
import ssl
from datetime import datetime, timezone
from http.client import HTTPSConnection
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .codec import JournalError, authenticate, canonical, fields, origin, origin_id, number, uuid, seal, unpack


class CatchupPaused(JournalError):
    """This bounded wake-up ended; resume from its already durable cursor."""


class MembershipUpdateRequired(JournalError):
    """Fetch the signed individual key wrap using saved device credentials."""


def encode(data):
    text = base64.b64encode(data).decode("ascii")
    return [text[index:index + 12000] for index in range(0, len(text), 12000)]


def decode(chunks):
    if type(chunks) is not list or len(chunks) > 8 or any(type(chunk) is not str or len(chunk) > 12000 for chunk in chunks):
        raise JournalError("Invalid message chunks")
    try:
        return base64.b64decode("".join(chunks), validate=True)
    except ValueError as error:
        raise JournalError("Invalid message encoding") from error


class LocalChannel:
    def __init__(self, device, *, transport_key, peers, epoch=1):
        if type(transport_key) is not bytes or len(transport_key) != 32:
            raise JournalError("Use an independent 32-byte transport key")
        if device.store.db.encrypted and transport_key == device.store.db.copy_key():
            raise JournalError("The transport secret must be independent of the profile data key")
        self.device, self.key, self.peers, self.epoch = device, transport_key, dict(peers), epoch

    def protect(self, payload, recipient):
        if hasattr(self, "membership"):
            self.membership.refresh(self)
        if recipient not in self.peers:
            raise JournalError("Recipient is not paired")
        config = self.device.store.config
        header = dict(version=2, type="journal-envelope", profile=config["profile"], generation=config["generation"],
                      sender=config["device"], recipient=recipient, epoch=self.epoch)
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, canonical(payload), canonical(header))
        return seal(header | dict(nonce=nonce.hex(), ciphertext=encode(ciphertext)), self.device.identity.sign)

    def open(self, wire):
        if hasattr(self, "membership"):
            self.membership.refresh(self)
        envelope = unpack(wire)
        body = envelope["body"]
        fields(body, ("version", "type", "profile", "generation", "sender", "recipient", "epoch", "nonce", "ciphertext"))
        uuid(body["sender"])
        uuid(body["recipient"])
        number(body["epoch"], minimum=1)
        public_key = self.peers.get(body["sender"])
        if public_key is None:
            raise JournalError("Sender is not paired")
        authenticate(envelope, public_key)  # Always authenticate before decryption.
        if self.device.home and not self.device.store.db.scalar(
            "SELECT 1 FROM journal_origins WHERE device=? AND public_key=? AND revoked=0", (body["sender"], public_key)):
            raise JournalError("Sender is no longer trusted")
        self.device.store._scope(body)
        if (body["version"] != 2 or body["type"] != "journal-envelope"
                or body["recipient"] != self.device.store.config["device"]):
            raise JournalError("Invalid routing or transport-key epoch")
        if body["epoch"] != self.epoch:
            raise MembershipUpdateRequired("Membership update required")
        try:
            nonce = bytes.fromhex(body["nonce"])
            if len(nonce) != 12:
                raise ValueError
            header = {key: value for key, value in body.items() if key not in {"nonce", "ciphertext"}}
            plain = AESGCM(self.key).decrypt(nonce, decode(body["ciphertext"]), canonical(header))
            payload = json.loads(plain)
            if canonical(payload) != plain:
                raise ValueError
        except (ValueError, TypeError, InvalidTag) as error:
            raise JournalError("Invalid encrypted payload") from error
        return body["sender"], payload

    def handle(self, wire):
        if self.device.home is None:
            raise JournalError("This device is not the home")
        sender, payload = self.open(wire)
        fields(payload, ("operation", "value"))
        home = self.device.home
        if payload["operation"] == "proposal":
            proposal = decode(payload["value"])
            inner = unpack(proposal)["body"]
            if type(inner) is not dict:
                raise JournalError("Invalid proposal body")
            origin(inner.get("origin"))
            if inner["origin"]["device"] != sender:
                raise JournalError("A local sender cannot impersonate another origin")
            result = dict(status=home.receive(proposal))
            home.process(limit=50)
        elif payload["operation"] == "changes":
            commits = home.store.commits_after(payload["value"], limit=1)
            result = dict(commits=[encode(commit) for commit in commits], cursor=home.store.cursor())
        elif payload["operation"] == "status":
            ids = payload["value"]
            if type(ids) is not list or len(ids) > 50 or any(type(value) is not str or not value.startswith(sender + "/") for value in ids):
                raise JournalError("Invalid status request")
            result = {identifier: home.status(identifier) for identifier in ids}
        elif payload["operation"] == "capabilities":
            from .compatibility import capabilities
            result = capabilities(home.store)
        elif payload['operation'] == 'ack':
            fields(payload['value'], ('incarnation', 'cursor'))
            incarnation = payload['value']['incarnation']
            if not home.store.db.scalar('SELECT 1 FROM journal_origins WHERE device=? AND incarnation=? AND public_key=? AND revoked=0',
                                       (sender, incarnation, self.peers[sender])):
                raise JournalError('Acknowledgement incarnation is not approved')
            from .retention import Retention
            result = dict(acknowledged=Retention(home.store).acknowledge(sender, incarnation, payload['value']['cursor']))
        elif payload['operation'] == 'receipts':
            revisions = payload['value']
            if type(revisions) is not list or len(revisions) > 8 or any(type(n) is not int or n < 1 for n in revisions):
                raise JournalError('Invalid receipt request')
            from .retention import Retention, is_receipt
            keeper = Retention(home.store, signer=home.signer)
            keeper.compact(limit=100)
            keeper.prune_local()
            result = {}
            for revision in revisions:
                saved = home.store.db.scalar('SELECT wire FROM journal_commits WHERE revision=?', (revision,))
                if saved and is_receipt(unpack(bytes(saved))['body']):
                    # An inherited prefix may carry the retired home's old
                    # signature. The current authorized home attests the same
                    # compact body under the key pinned for this generation.
                    result[str(revision)] = encode(seal(unpack(bytes(saved))['body'], home.signer))
        else:
            raise JournalError("Unsupported local operation")
        return self.protect(dict(request_nonce=unpack(wire)["body"]["nonce"], result=result), sender)

    async def synchronize(self, request, *, home_id, max_requests=1000):
        """`request` sends bytes over a certificate-pinned TLS connection."""
        if type(max_requests) is not int or not 1 <= max_requests <= 1000:
            raise JournalError("Invalid sync work budget")
        exchanges = 0
        async def exchange(operation, value):
            nonlocal exchanges
            if exchanges >= max_requests:
                raise CatchupPaused("Catch-up paused at its durable cursor; more work remains")
            exchanges += 1
            payload = dict(operation=operation, value=value)
            outgoing = request.prepare(payload, home_id) if hasattr(request, "prepare") else self.protect(payload, home_id)
            response = await request(outgoing)
            sender, result = self.open(response)
            if sender != home_id:
                raise JournalError("Response is not from the home")
            fields(result, ("request_nonce", "result"))
            if result["request_nonce"] != unpack(outgoing)["body"]["nonce"]:
                raise JournalError("Response belongs to an earlier request")
            return result["result"]
        pending = self.device.store.pending()
        from .compatibility import capabilities, check
        local = capabilities(self.device.store)
        remote = await exchange('capabilities', local)
        check(local, remote, pending)
        for proposal in pending:
            await exchange("proposal", encode(proposal))
        for offset in range(0, len(pending), 50):
            ids = [origin_id(unpack(wire)["body"]["origin"]) for wire in pending[offset:offset + 50]]
            states = await exchange("status", ids)
            with self.device.store.db.transaction():
                for identifier, state in states.items():
                    if state:
                        self.device.store.db.execute("INSERT OR REPLACE INTO journal_remote_states VALUES(?,?,?)",
                                                    (identifier, state["status"], state["reason"]))
        while True:
            response = await exchange("changes", self.device.store.cursor())
            if not response["commits"]:
                if response["cursor"] != self.device.store.cursor():
                    raise JournalError("Verified checkpoint required")
                if remote['entry_kinds'].get('control.ack') == 1:
                    await exchange('ack', dict(incarnation=self.device.store.config['incarnation'], cursor=self.device.store.cursor()))
                if remote['entry_kinds'].get('control.receipts') == 1:
                    from .retention import Retention
                    retention = Retention(self.device.store)
                    revisions = retention.expired_revisions()
                    if revisions:
                        receipts = await exchange('receipts', revisions)
                        if type(receipts) is not dict or set(receipts) - {str(n) for n in revisions}:
                            raise JournalError('Unrequested receipt response')
                        for receipt in receipts.values():
                            retention.accept_receipt(decode(receipt))
                    retention.prune_local()
                with self.device.store.db.transaction():
                    self.device.store.db.execute("INSERT OR REPLACE INTO journal_local VALUES('last_sync',?)", (datetime.now(timezone.utc).isoformat(),))
                return
            for commit in response["commits"]:
                self.device.store.apply(decode(commit))


class PinnedLocalClient:
    """TLS 1.3 to one paired device; its pinned certificate is the only trust root."""
    def __init__(self, url, certificate_pem, *, timeout=5):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise JournalError("Use the paired device's HTTPS address")
        self.host, self.port, self.path = parsed.hostname, parsed.port or 47513, parsed.path or "/exchange"
        if type(timeout) not in (int, float) or not 0.1 <= timeout <= 10:
            raise JournalError("Invalid local connection timeout")
        self.timeout = timeout
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.check_hostname = False  # Identity is the exact paired self-signed certificate.
        self.context.verify_mode = ssl.CERT_REQUIRED
        self.context.minimum_version = ssl.TLSVersion.TLSv1_3
        self.context.load_verify_locations(cadata=certificate_pem)

    async def __call__(self, wire):
        return await asyncio.to_thread(self._send, wire)

    def _send(self, wire):
        if len(wire) > 64 * 1024:
            raise JournalError("Local envelope limit exceeded")
        connection = HTTPSConnection(self.host, self.port, context=self.context, timeout=self.timeout)
        try:
            connection.request("POST", self.path, body=wire, headers={"Content-Type": "application/octet-stream"})
            response = connection.getresponse()
            if response.status == 409 and response.getheader("X-Journal-Action") == "membership":
                raise MembershipUpdateRequired("Membership update required")
            if response.status != 200:
                raise JournalError("The local home refused this sync request")
            result = response.read(64 * 1024 + 1)
            if len(result) > 64 * 1024:
                raise JournalError("Local response limit exceeded")
            return result
        finally:
            connection.close()
