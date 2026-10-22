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

from .codec import (MAX_MESSAGE, JournalError, authenticate, canonical, cursor as check_cursor, fields, hash_value, origin,
                    origin_id, number, uuid, seal, unpack)
from .finance import ChunksMissing

# Plaintext budgets for one combined round. A sealed message is AES-GCM + base64 + signature,
# so about 4/3 of its plaintext plus ~2 KiB of header must stay within MAX_MESSAGE. A commit is
# base64-wrapped again, so the largest single commit a reply can carry is about 33 KiB of wire.
REPLY_BUDGET = 40 * 1024
REQUEST_BUDGET = 36 * 1024
ROUND_PROPOSALS = 50
SEALED_OVERHEAD = 2048


def fits(payload):
    return 4 * ((len(canonical(payload)) + 18) // 3) + SEALED_OVERHEAD <= MAX_MESSAGE


class CatchupPaused(JournalError):
    """This bounded wake-up ended; resume from its already durable cursor."""


class UploadHeld(JournalError):
    """Downloads finished, but the home would not take every pending edit yet; they stay pending."""


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
        elif payload["operation"] == "round":
            result = self._round(home, sender, payload["value"])
            nonce = unpack(wire)["body"]["nonce"]
            while result["commits"] and (len(result["commits"]) > 1 or result["pieces"]) and not fits(dict(request_nonce=nonce, result=result)):
                result["commits"].pop()
            while len(result["pieces"]) > 1 and not fits(dict(request_nonce=nonce, result=result)):
                result["pieces"].pop()
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
        else:
            raise JournalError("Unsupported local operation")
        return self.protect(dict(request_nonce=unpack(wire)["body"]["nonce"], result=result), sender)

    def refusal(self, wire, error):
        """An authenticated request the home could not take now gets an answer, so
        the device retries it with a fresh request instead of waiting forever."""
        sender, _ = self.open(wire)
        return self.protect(dict(request_nonce=unpack(wire)["body"]["nonce"], result=dict(refused=str(error)[:200])), sender)

    def _round(self, home, sender, value):
        """Receive what fits, process, report statuses and as many commits as one reply holds."""
        from .compatibility import capabilities, check
        fields(value, ("capabilities", "proposals", "status", "cursor", "pieces"))
        if type(value["pieces"]) is not list or len(value["pieces"]) > 4:
            raise JournalError("Invalid sync round")
        for item in value["pieces"]:
            hash_value(item)
        proposals, ids = value["proposals"], value["status"]
        if (type(proposals) is not list or len(proposals) > ROUND_PROPOSALS or type(ids) is not list or len(ids) > 50
                or any(type(item) is not str or not item.startswith(sender + "/") for item in ids)):
            raise JournalError("Invalid sync round")
        wires = [decode(item) for item in proposals]
        for wire in wires:
            inner = unpack(wire)["body"]
            if type(inner) is not dict:
                raise JournalError("Invalid proposal body")
            origin(inner.get("origin"))
            if inner["origin"]["device"] != sender:
                raise JournalError("A local sender cannot impersonate another origin")
        check_cursor(value["cursor"])
        mine = capabilities(home.store)
        result = dict(capabilities=mine, reject=None, held=None, states={}, commits=[], pieces=[], cursor=home.store.cursor())
        try:
            check(value["capabilities"], mine, wires)
        except (JournalError, TypeError, KeyError) as error:
            result["reject"] = str(error) or "Incompatible peer"
            return result
        for wire in wires:
            try:
                home.receive(wire)
            except JournalError as error:  # Later proposals wait; downloads continue.
                result["held"] = str(error)
                break
        if wires:
            home.process(limit=50)
        result["states"] = {identifier: home.status(identifier) for identifier in ids}
        result["cursor"] = home.store.cursor()
        try:
            commits = home.store.commits_after(value["cursor"], limit=50)
        except JournalError as error:
            result["reject"] = str(error)
            return result
        size = 0
        for item in value["pieces"]:  # Chunks of a large effect the device is waiting for, first.
            data = home.store.chunk(item)
            if data is not None:
                result["pieces"].append(encode(data))
                size += sum(map(len, result["pieces"][-1]))
        for commit in commits:
            encoded = encode(commit)
            size += sum(map(len, encoded))
            if result["commits"] and size > REPLY_BUDGET:
                break
            result["commits"].append(encoded)
        return result

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
            if type(result["result"]) is dict and set(result["result"]) == {"refused"}:
                from .cloud import HomeRefused
                raise HomeRefused(str(result["result"]["refused"])[:200])
            return result["result"]
        from .compatibility import capabilities, check
        store = self.device.store
        local, held, wanted, applied = capabilities(store), None, [], False
        while True:
            pending = store.pending()
            known = {row[0] for row in store.db.all("SELECT proposal_id FROM journal_remote_states")}
            entries = [(origin_id(unpack(wire)["body"]["origin"]), wire) for wire in pending]
            unsent = [] if held else [(identifier, wire) for identifier, wire in entries if identifier not in known]
            batch, size = [], 0
            for identifier, wire in unsent:
                chunks = encode(wire)
                if batch and (len(batch) >= ROUND_PROPOSALS or size + sum(map(len, chunks)) > REQUEST_BUDGET):
                    break
                batch.append((identifier, chunks))
                size += sum(map(len, chunks))
            ids = [identifier for identifier, _ in batch]
            ids += [identifier for identifier, _ in entries if identifier in known][:50 - len(ids)]
            result = await exchange("round", dict(capabilities=local, proposals=[chunks for _, chunks in batch], status=ids,
                                                  cursor=store.cursor(), pieces=wanted))
            if type(result) is not dict or {"capabilities", "reject", "held", "states", "commits", "cursor"} - set(result):
                raise JournalError("Invalid sync round reply")
            check(local, result["capabilities"], pending)
            if result["reject"]:
                raise JournalError(result["reject"])
            states = result["states"]
            if type(states) is not dict or set(states) - set(ids):
                raise JournalError("Invalid sync round reply")
            with store.db.transaction():
                for identifier, state in states.items():
                    if state:
                        store.db.execute("INSERT OR REPLACE INTO journal_remote_states VALUES(?,?,?)", (identifier, state["status"], state["reason"]))
                    else:
                        store.db.execute("DELETE FROM journal_remote_states WHERE proposal_id=?", (identifier,))
            for piece in result.get("pieces", []):
                store.put_chunk(decode(piece), wanted)
            wanted = []
            for commit in result["commits"]:
                try:
                    applied = store.apply(decode(commit)) or applied
                except ChunksMissing as error:  # A large effect: fetch its chunks next round.
                    wanted = error.missing[:4]
                    break
            held = held or result["held"]
            if store.cursor() != result["cursor"]:
                if not result["commits"] and not result.get("pieces") and not wanted:
                    raise JournalError("Verified checkpoint required")
                continue
            if len(batch) < len(unsent) and not held:
                continue
            if applied:
                store.verify()
            with store.db.transaction():
                store.db.execute("INSERT OR REPLACE INTO journal_local VALUES('last_sync',?)", (datetime.now(timezone.utc).isoformat(),))
            if held:
                raise UploadHeld(held)
            return


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
