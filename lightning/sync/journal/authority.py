"""Durable fencing and explicit owner-authorized generation transitions.

The independent control file is never in a profile backup. Losing it blocks
confirmation; profile restore cannot rewind the highest observed generation.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from lightning.sync.identity import verify_signature
from .codec import (JournalError, authenticate, canonical, cursor, digest, fields,
                    hash_value, number, seal, unpack, uuid)


def _public(key):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),bytes.fromhex(key)).public_bytes(
        serialization.Encoding.X962,serialization.PublicFormat.CompressedPoint)


def transition(body):
    fields(body, ("profile", "previous", "generation", "home", "home_key", "owner_key", "version", "mode", "nonce", "cutoff"))
    for key in ("profile", "previous", "generation", "home"):
        uuid(body[key])
    number(body["version"], minimum=2)
    hash_value(body["nonce"])
    cursor(body["cutoff"])
    if body["previous"] == body["generation"] or body["mode"] not in ("move", "recover", "rotate-owner"):
        raise JournalError("Invalid authority transition")
    from cryptography.hazmat.primitives.asymmetric import ec
    for key in ("home_key", "owner_key"):
        try:
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(body[key]))
        except (ValueError, TypeError) as error:
            raise JournalError("Invalid authority public key") from error


class AuthorityMemory:
    def __init__(self, path, *, profile):
        self.path, self.profile = Path(path), profile
        if not self.path.is_file() or self.path.is_symlink():
            raise JournalError("Authority memory is missing; explicit repair required")
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self._confirm_depth = 0
        self.db.execute("PRAGMA synchronous=FULL")
        try:
            self.state()
        except BaseException:
            self.db.close()
            raise

    @classmethod
    def enroll(cls, path, wire):
        envelope = unpack(wire)
        body = envelope["body"]
        fields(body, ("type", "version", "profile", "generation", "home", "home_key", "owner_key"))
        if body["type"] != "authority-enrollment" or body["version"] != 1:
            raise JournalError("Invalid authority enrollment")
        for key in ("profile", "generation", "home"):
            uuid(body[key])
        authenticate(envelope, body["owner_key"])
        path = Path(path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        db = sqlite3.connect(path, isolation_level=None)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE authority(id INTEGER PRIMARY KEY CHECK(id=1),document TEXT NOT NULL)")
            db.execute("CREATE TABLE certificates(version INTEGER PRIMARY KEY,wire BLOB NOT NULL)")
            state = body | dict(phase="active", cutoff=dict(revision=0, hash="0" * 64), predecessor=None)
            db.execute("INSERT INTO authority VALUES(1,?)", (canonical(state).decode(),))
            db.execute("INSERT INTO certificates VALUES(1,?)", (wire,))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
        return cls(path, profile=body["profile"])

    def close(self):
        self.db.close()

    def state(self):
        try:
            row = self.db.execute("SELECT document FROM authority WHERE id=1").fetchone()
            if row is None:
                raise ValueError
            value = json.loads(row[0])
            if value["profile"] != self.profile or value["phase"] not in ("active", "frozen", "retired", "candidate", "prepared"):
                raise ValueError
            number(value["version"], minimum=1)
            uuid(value["generation"])
            cursor(value["cutoff"])
            return value
        except (sqlite3.Error, ValueError, KeyError, TypeError) as error:
            raise JournalError("Authority memory is damaged; confirmation blocked") from error

    def _change(self, apply):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            value = self.state()
            result = apply(value)
            self.db.execute("UPDATE authority SET document=? WHERE id=1", (canonical(value).decode(),))
            self.db.execute("COMMIT")
            return result
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def bind(self, store):
        state = self.state()
        if state["profile"] != store.config["profile"]:
            raise JournalError("Authority memory belongs to another profile")
        store.authority = self
        with store.db.transaction():
            store.db.execute("INSERT OR REPLACE INTO journal_local VALUES('authority_enrolled','1')")

    def can_confirm(self, store):
        state = self.state()
        return (state["phase"] == "active" and state["generation"] == store.config["generation"]
                and state["home"] == store.config["device"] and state["home_key"] == store.config["home_key"])

    @contextmanager
    def confirming(self, store):
        """Serialize freeze/retirement with the complete financial commit."""
        outer = self._confirm_depth == 0
        if outer:
            self.db.execute("BEGIN IMMEDIATE")
        try:
            if not self.can_confirm(store):
                raise JournalError("Confirmation is frozen or this home is retired")
            self._confirm_depth += 1
            try:
                yield
            finally:
                self._confirm_depth -= 1
            if outer:
                self.db.execute("COMMIT")
        except BaseException:
            if outer and self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def freeze(self, store):
        state = self.state()
        if (state["phase"] == "frozen" and state["generation"] == store.config["generation"]
                and state["home"] == store.config["device"]):
            return state["cutoff"]
        if not self.can_confirm(store):
            raise JournalError("Only the active home can freeze")
        def apply(state):
            if state["phase"] != "active" or state["generation"] != store.config["generation"]:
                raise JournalError("The authority already changed")
            state["phase"], state["cutoff"] = "frozen", store.cursor()
        self._change(apply)
        return self.state()["cutoff"]

    def verify_transition(self, wire, *, allow_observed=False):
        envelope = unpack(wire)
        transition(envelope["body"])
        state = self.state()
        body = envelope["body"]
        if allow_observed and body["version"] == state["version"] and body["generation"] == state["generation"]:
            saved = self.db.execute("SELECT wire FROM certificates WHERE version=?",(body["version"],)).fetchone()
            if saved and digest(unpack(bytes(saved[0]))["body"]) == digest(body):
                return body
            raise JournalError("Competing authority transition")
        authenticate(envelope, state["owner_key"])
        if body["profile"] != self.profile or body["previous"] != state["generation"] or body["version"] != state["version"] + 1:
            raise JournalError("Stale or competing authority transition")
        return body

    def prepare(self, store, wire, signer):
        body = self.verify_transition(wire)
        if (body["home"] != store.config["device"] or _public(body["home_key"]) != _public(store.config["origin_key"]) or store.cursor() != body["cutoff"]
                or store.config["generation"] != body["previous"]):
            raise JournalError("Target must install and verify the final checkpoint before preparing")
        state = self.state()
        if state["phase"] == "prepared":
            if state.get("prepared") != digest(body):
                raise JournalError("Target already prepared a competing transition")
            saved = state.get("prepared_receipt")
            if saved:
                return saved.encode()
        receipt = dict(type="authority-prepared", transition=digest(body), cursor=store.cursor(), fingerprint=store.fingerprint())
        result = seal(receipt, signer)
        def apply(state):
            if state["phase"] not in ("active", "prepared") or (state["phase"] == "prepared" and state.get("prepared") != digest(body)):
                raise JournalError("Target is not available to prepare")
            state["phase"], state["prepared"] = "prepared", digest(body)
            state["prepared_receipt"] = result.decode()
        self._change(apply)
        return result

    def retire(self, store, wire, prepared, signer):
        body = self.verify_transition(wire)
        state = self.state()
        if state["phase"] not in ("frozen","retired") or state["home"] != store.config["device"] or state["cutoff"] != body["cutoff"]:
            raise JournalError("Freeze the home at the final checkpoint before retirement")
        envelope = unpack(prepared)
        authenticate(envelope, body["home_key"])
        fields(envelope["body"], ("type", "transition", "cursor", "fingerprint"))
        expected = dict(type="authority-prepared", transition=digest(body), cursor=store.cursor(), fingerprint=store.fingerprint())
        if envelope["body"] != expected:
            raise JournalError("Target prepared another checkpoint")
        if state["phase"] == "retired":
            if state.get("retirement") != digest(body) or not state.get("retirement_receipt"):
                raise JournalError("Home retired for another transition; explicit repair required")
            return state["retirement_receipt"].encode()
        receipt = seal(dict(type="authority-retired", transition=digest(body), prepared=digest(envelope["body"])), signer)
        def apply(current):
            if current["phase"] != "frozen":
                raise JournalError("Home was already retired")
            current["phase"], current["retirement"] = "retired", digest(body)
            current["retirement_receipt"] = receipt.decode()
        self._change(apply)  # Retirement is durable before its signature escapes.
        return receipt

    def observe(self, wire, *, local_device):
        """Pin a successor before opening its profile; no timeout may activate it."""
        body = self.verify_transition(wire)
        def apply(state):
            if state["generation"] != body["previous"]:
                raise JournalError("A newer authority was already observed")
            self.db.execute("INSERT INTO certificates VALUES(?,?)", (body["version"], wire))
            state["previous_home_key"] = state["home_key"]
            state.update(body)
            state["phase"] = "candidate" if body["home"] == local_device else "retired"
            state["predecessor"] = body["previous"]
        self._change(apply)

    def activate_move(self, store, wire, prepared, retired, *, old_home_key, home_signer=None, fault=lambda phase: None):
        body = self.verify_transition(wire,allow_observed=True)
        state = self.state()
        if state["phase"] not in ("prepared","candidate","active") or state.get("prepared") != digest(body) or body["mode"] != "move":
            raise JournalError("Target has not prepared this move")
        trusted_old_key = state["home_key"] if state["phase"] == "prepared" else state.get("previous_home_key")
        if trusted_old_key is None or _public(old_home_key) != _public(trusted_old_key):
            raise JournalError("Retirement signer differs from the pinned old home")
        confirmation = unpack(retired)
        authenticate(confirmation, trusted_old_key)
        if confirmation["body"] != dict(type="authority-retired", transition=digest(body), prepared=digest(unpack(prepared)["body"])):
            raise JournalError("No matching durable old-home retirement")
        if state["phase"] == "prepared":
            self.observe(wire, local_device=store.config["device"])
        fault("authority_observed")
        self._activate(store, body, home_signer=home_signer, fault=fault)

    async def recover(self, store, wire, registry, *, home_signer=None, fault=lambda phase: None):
        """Obtain a live CAS result from the configured authenticated registry."""
        body = self.verify_transition(wire,allow_observed=True)
        if body["mode"] != "recover" or body["home"] != store.config["device"] or body["cutoff"] != store.cursor():
            raise JournalError("Recovery requires the verified surviving prefix")
        await registry.publish(wire)
        if self.state()["generation"] == body["previous"]:
            self.observe(wire, local_device=store.config["device"])
        fault("authority_observed")
        self._activate(store, body, home_signer=home_signer, fault=fault)

    def _activate(self, store, body, *, home_signer=None, fault=lambda phase: None):
        state = self.state()
        if (state["phase"] not in ("candidate","active") or body["home"] != store.config["device"]
                or state["generation"] != body["generation"] or state["version"] != body["version"]
                or _public(body["home_key"]) != _public(store.config["origin_key"])):
            raise JournalError("Only the pinned target can activate")
        if store.config["generation"] not in (body["previous"],body["generation"]):
            raise JournalError("Profile is outside the verified transition")
        if state["phase"] == "active" and store.config["generation"] != body["generation"]:
            raise JournalError("Active authority and profile disagree; explicit repair required")
        config = dict(store.config, generation=body["generation"], home_key=body["home_key"], role="home")
        previous_config = store.config
        try:
            with store.db.transaction():
                store.db.execute("UPDATE journal_meta SET config=? WHERE id=1", (canonical(config).decode(),))
                store.config = config
                membership = store.db.scalar("SELECT value FROM journal_local WHERE name='membership'")
                reset = store.db.scalar("SELECT value FROM journal_local WHERE name='transport_generation'")
                if membership and reset != body["generation"]:
                    if home_signer is None:
                        raise JournalError("The successor signing key is required to rotate transport keys")
                    from types import SimpleNamespace
                    from .membership import Membership
                    Membership(SimpleNamespace(store=store)).begin_generation(home_signer)
        except BaseException:
            store.config = previous_config
            raise
        fault("authority_profile_committed")
        store.config = config
        # Crash before this last control commit leaves a blocked candidate.
        def activate(current):
            if current["generation"] != body["generation"] or current["version"] != body["version"] or current["phase"] not in ("candidate","active"):
                raise JournalError("A newer authority was observed during activation")
            current["phase"] = "active"
        self._change(activate)
        fault("authority_activated")

    def admits_original(self, body):
        """Allow signed original proposals only from a generation in pinned transition history."""
        if type(body) is not dict or body.get("profile") != self.profile:
            return False
        try:
            return body.get("generation") in self.generation_home_keys()
        except JournalError:
            return False

    def generation_home_keys(self):
        """Verify the owner-signed certificate chain and return its generation keys.

        This control database is the independently pinned authority root. A saved
        ledger alone cannot authorize a historical generation or home signer.
        """
        rows = self.db.execute("SELECT version,wire FROM certificates ORDER BY version").fetchall()
        if not rows or [row[0] for row in rows] != list(range(1, len(rows) + 1)):
            raise JournalError("Pinned authority certificate history is incomplete")
        enrollment = unpack(bytes(rows[0][1]))
        first = enrollment["body"]
        fields(first, ("type", "version", "profile", "generation", "home", "home_key", "owner_key"))
        if first["type"] != "authority-enrollment" or first["version"] != 1 or first["profile"] != self.profile:
            raise JournalError("Pinned authority enrollment is invalid")
        authenticate(enrollment, first["owner_key"])
        generations = {first["generation"]: first["home_key"]}
        prior_generation, prior_owner, prior_version = first["generation"], first["owner_key"], 1
        for row in rows[1:]:
            certificate = unpack(bytes(row[1]))
            value = certificate["body"]
            transition(value)
            authenticate(certificate, prior_owner)
            if (value["profile"] != self.profile or value["previous"] != prior_generation
                    or value["version"] != prior_version + 1 or value["generation"] in generations):
                raise JournalError("Pinned authority transition chain is invalid")
            generations[value["generation"]] = value["home_key"]
            prior_generation, prior_owner, prior_version = value["generation"], value["owner_key"], value["version"]
        state = self.state()
        if (state["generation"] != prior_generation or state["version"] != prior_version
                or state["owner_key"] != prior_owner or state["home_key"] != generations[prior_generation]):
            raise JournalError("Pinned authority state does not match its certificates")
        return generations


def transfer_home_state(source, target):
    """Copy final inbox/receipts only after financial snapshot verification.

    Device-local queues and counters remain on their original devices.
    """
    if source.authority.state()["phase"] != "frozen" or source.cursor() != target.cursor() or source.fingerprint() != target.fingerprint():
        raise JournalError("A frozen identical checkpoint is required for handover")
    with target.db.transaction():
        for table in ("journal_origins", "journal_inbox", "journal_reviews"):
            target.db.execute(f"DELETE FROM {table}")
            for row in source.db.all(f"SELECT * FROM {table}"):
                target.db.execute(f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})", tuple(row))


class AuthorityRegistry:
    """Online registry over MailboxClient's configured TLS origin.

    Publication uses an owner signature, independently of device admission.
    A lost reply is reconciled by reading the durable winning certificate.
    """
    def __init__(self, client):
        self.client = client

    async def catch_up(self, memory, *, local_device):
        """Verify and durably pin every owner-signed link; never skip a key change."""
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        for _ in range(16):
            state = memory.state()
            response = await self.client.call("/authority/chain",dict(after=state["version"]))
            fields(response,("certificates","latest"))
            number(response["latest"],minimum=state["version"])
            certificates = response["certificates"]
            if type(certificates) is not list or len(certificates) > 8:
                raise JournalError("Invalid authority certificate page")
            if not certificates:
                if response["latest"] != state["version"]:
                    raise JournalError("Authority chain is incomplete")
                return state
            for certificate in certificates:
                fields(certificate,("body","signature"))
                signature = certificate["signature"]
                if type(signature) is not str or len(signature) != 128:
                    raise JournalError("Invalid registry certificate signature")
                try:
                    raw = bytes.fromhex(signature)
                    der = encode_dss_signature(int.from_bytes(raw[:32],"big"),int.from_bytes(raw[32:],"big")).hex()
                except ValueError as error:
                    raise JournalError("Invalid registry certificate signature") from error
                wire = canonical(dict(body=certificate["body"],signature=der))
                memory.observe(wire,local_device=local_device)
            if memory.state()["version"] == response["latest"]:
                return memory.state()
        raise JournalError("Authority catch-up paused; reconnect to continue")

    async def publish(self, wire):
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        from .cloud import CloudUnavailable
        envelope = unpack(wire)
        body = envelope["body"]
        transition(body)
        r, s = decode_dss_signature(bytes.fromhex(envelope["signature"]))
        request = dict(body=body, signature=(r.to_bytes(32, "big") + s.to_bytes(32, "big")).hex())
        try:
            await self.client.call("/authority/transition", request)
        except CloudUnavailable:
            # A timeout/409 may mean another attempt won; never assume our own.
            pass
        current = await self.client.call("/authority")
        if (current.get("generation") != body["generation"] or current.get("version") != body["version"]
                or current.get("certificate") != request):
            raise JournalError("Registry selected another successor; preserve this copy")
        return current
