"""Signed membership epochs and individual ECDH-wrapped group-key rotation."""
from __future__ import annotations

import json
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .codec import JournalError, authenticate, canonical, fields, number, seal, unpack, uuid
from .errors import DeviceRevoked


def _key(shared, context):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"lightning/journal/individual-transport/v1\n" + context).derive(shared)


class Membership:
    def __init__(self, device):
        self.device, self.db = device, device.store.db

    def state(self):
        value = self.db.scalar("SELECT value FROM journal_local WHERE name='membership'")
        if value is None:
            raise JournalError("Membership metadata missing; pairing or repair required")
        return json.loads(value)

    def initialize(self, members, secret):
        if self.db.scalar("SELECT value FROM journal_local WHERE name='membership'"):
            raise JournalError("Membership already initialized")
        if type(secret) is not bytes or len(secret) != 32 or secret == self.db.copy_key():
            raise JournalError("Use an independent transport secret")
        self._validate_members(members)
        with self.db.transaction():
            self._save(dict(version=1, epoch=1, members=members, retired=[]), secret)

    @staticmethod
    def _validate_members(members):
        if type(members) is not dict or not 1 <= len(members) <= 16:
            raise JournalError("Invalid paired-device set")
        for identifier, member in members.items():
            uuid(identifier)
            fields(member, ("key", "incarnation"))
            uuid(member["incarnation"])
            try:
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(member["key"]))
            except (ValueError, TypeError) as error:
                raise JournalError("Invalid paired-device key") from error

    def _save(self, state, secret):
        self.db.execute("INSERT OR REPLACE INTO journal_local VALUES('membership',?)", (canonical(state).decode(),))
        self.db.execute("INSERT OR REPLACE INTO journal_local VALUES('transport',?)", (secret.hex(),))

    def refresh(self, channel):
        state = self.state()
        channel.key = bytes.fromhex(self.db.scalar("SELECT value FROM journal_local WHERE name='transport'"))
        channel.epoch = state["epoch"]
        channel.peers = {identifier: member["key"] for identifier, member in state["members"].items()
                         if identifier != self.device.identity.device_id}

    def bind(self, channel):
        channel.membership = self
        self.refresh(channel)

    def rotate(self, members):
        if self.device.home is None:
            raise JournalError("Only the home changes membership")
        self.device.store.require_confirmation_authority()
        self._validate_members(members)
        state = self.state()
        own = self.device.identity.device_id
        if members.get(own) != state["members"].get(own):
            raise JournalError("Use an authority move to replace the home")
        retired = set(state["retired"])
        for identifier, member in state["members"].items():
            if members.get(identifier) != member:
                if identifier in members and members[identifier]["key"] == member["key"]:
                    raise JournalError("A new incarnation needs a fresh device key")
                retired.add(identifier + "/" + member["incarnation"])
        if any(identifier + "/" + member["incarnation"] in retired for identifier, member in members.items()):
            raise JournalError("A retired device incarnation cannot be revived")
        secret = os.urandom(32)
        header = dict(type="journal-membership", profile=self.device.store.config["profile"],
                      generation=self.device.store.config["generation"], previous=state["version"],
                      version=state["version"] + 1, epoch=state["epoch"] + 1, members=members, retired=sorted(retired))
        wire = self._wrap(header,secret,self.device.identity.sign)
        with self.db.transaction():
            for identifier, member in state["members"].items():
                if members.get(identifier) != member:
                    self.device.home.revoke_origin(identifier, member["incarnation"])
            for identifier, member in members.items():
                self.device.home.approve_origin(identifier, member["incarnation"], member["key"])
            self._save(dict(version=header["version"], epoch=header["epoch"], members=members, retired=header["retired"]), secret)
            self.db.execute("INSERT OR REPLACE INTO journal_local VALUES('membership_wire',?)", (wire.decode(),))
            self.db.execute("INSERT OR REPLACE INTO journal_local VALUES(?,?)", ("membership_wire:" + str(header["version"]),wire.decode()))
        return wire

    @staticmethod
    def _wrap(header,secret,signer):
        wrapped = {}
        for identifier, member in header["members"].items():
            ephemeral = ec.generate_private_key(ec.SECP256R1())
            public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(member["key"]))
            context = canonical(header | dict(recipient=identifier))
            nonce = os.urandom(12)
            wrapped[identifier] = dict(ephemeral=ephemeral.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint).hex(), nonce=nonce.hex(),
                ciphertext=AESGCM(_key(ephemeral.exchange(ec.ECDH(), public), context)).encrypt(nonce, secret, context).hex())
        return seal(header | dict(wrapped=wrapped), signer)

    def begin_generation(self,signer):
        """Called only inside the owner's verified activation transaction."""
        store = self.device.store
        authority = store.authority.state() if store.authority is not None else None
        if (authority is None or authority["phase"] != "candidate" or authority["generation"] != store.config["generation"]
                or authority["home"] != store.config["device"]):
            raise JournalError("Transport reset requires a pinned candidate authority")
        state = self.state()
        own = state["members"].get(store.config["device"])
        if own is None or own["key"] != store.config["origin_key"] or own["incarnation"] != store.config["incarnation"]:
            raise JournalError("The successor is not an approved device incarnation")
        secret = os.urandom(32)
        header = dict(type="journal-membership",profile=store.config["profile"],generation=store.config["generation"],
                      previous=0,version=1,epoch=1,members=state["members"],retired=state["retired"])
        wire = self._wrap(header,secret,signer)
        authenticate(unpack(wire),store.config["origin_key"])
        self._save(dict(version=1,epoch=1,members=state["members"],retired=state["retired"]),secret)
        self.db.execute("INSERT OR REPLACE INTO journal_local VALUES('membership_wire:1',?)",(wire.decode(),))
        self.db.execute("INSERT OR REPLACE INTO journal_local VALUES('membership_wire',?)",(wire.decode(),))
        self.db.execute("INSERT OR REPLACE INTO journal_local VALUES('transport_generation',?)",(store.config["generation"],))

    def control(self, wire):
        if self.device.home is None or len(wire) > 4096:
            raise JournalError("Membership request refused")
        self.device.store.require_confirmation_authority()
        envelope = unpack(wire)
        body = envelope["body"]
        fields(body,("type","profile","generation","sender","recipient","version","nonce"))
        self.device.store._scope(body)
        number(body["version"],minimum=1)
        from .codec import hash_value
        hash_value(body["nonce"])
        if body["type"] != "journal-membership-fetch" or body["recipient"] != self.device.identity.device_id:
            raise JournalError("Membership requester is not paired")
        member = self.db.one("SELECT public_key FROM journal_origins WHERE device=? AND revoked=0",(body["sender"],))
        if member is not None:
            authenticate(envelope,member["public_key"])
        elif not self._removed(envelope, body["sender"]):
            raise JournalError("Membership requester is not paired")
        state = self.state()
        if body["version"] >= state["version"]:
            raise JournalError("No newer membership transition")
        update = self.db.scalar("SELECT value FROM journal_local WHERE name=?",("membership_wire:" + str(body["version"] + 1),))
        if update is None:
            raise JournalError("Membership history missing; explicit repair required")
        return seal(dict(type="journal-membership-reply",nonce=body["nonce"],latest=state["version"],update=update),self.device.identity.sign)

    def _removed(self, envelope, sender):
        """A removed device may fetch the next signed transition: it leaves the device out and wraps no key for it."""
        for row in self.db.all("SELECT public_key FROM journal_origins WHERE device=? AND revoked=1", (sender,)):
            try:
                authenticate(envelope, row["public_key"])
                return True
            except JournalError:
                continue
        return False

    def revoked(self):
        """The home's signed membership left this device out (saved when it was learned), else None."""
        value = self.db.scalar("SELECT value FROM journal_local WHERE name='membership_revoked'")
        return json.loads(value) if value else None

    async def catch_up(self, send, home_id):
        for _ in range(16):
            state = self.state()
            nonce = secrets.token_hex(32)
            config = self.device.store.config
            body = dict(type="journal-membership-fetch",profile=config["profile"],generation=config["generation"],
                        sender=config["device"],recipient=home_id,version=state["version"],nonce=nonce)
            envelope = unpack(await send(seal(body,self.device.identity.sign)))
            authenticate(envelope,config["home_key"])
            response = envelope["body"]
            fields(response,("type","nonce","latest","update"))
            if response["type"] != "journal-membership-reply" or response["nonce"] != nonce:
                raise JournalError("Membership reply belongs to another request")
            self.accept(response["update"].encode())
            if self.state()["version"] == response["latest"]:
                return
        raise JournalError("Membership catch-up paused; reconnect to continue")

    def accept(self, wire, *, initial=False):
        envelope = unpack(wire)
        authenticate(envelope, self.device.store.config["home_key"])
        body = envelope["body"]
        fields(body, ("type", "profile", "generation", "previous", "version", "epoch", "members", "retired", "wrapped"))
        self.device.store._scope(body)
        present = self.db.scalar("SELECT value FROM journal_local WHERE name='membership'")
        if initial and present is None:
            number(body["previous"], minimum=0)
            number(body["epoch"], minimum=1)
            state = dict(version=body["previous"], epoch=body["epoch"] - 1, retired=[])
        else:
            state = self.state()
        if body["type"] != "journal-membership" or body["previous"] != state["version"] or body["version"] != state["version"] + 1 or body["epoch"] != state["epoch"] + 1:
            raise JournalError("Stale or skipped membership transition")
        self._validate_members(body["members"])
        own = self.device.identity.device_id
        if (own not in body["members"] or body["members"][own]["key"] != self.device.identity.public_key
                or body["members"][own]["incarnation"] != self.device.store.config["incarnation"]):
            if not initial:
                # Signed by the home and the very next transition after this device's copy: proof it was removed.
                with self.db.transaction():
                    self.db.execute("INSERT OR REPLACE INTO journal_local VALUES('membership_revoked',?)",
                                    (canonical(dict(version=body["version"])).decode(),))
                raise DeviceRevoked("This device is no longer a member")
            raise JournalError("This device is no longer a member")
        retired = body["retired"]
        if type(retired) is not list or not set(state["retired"]) <= set(retired):
            raise JournalError("Membership cannot forget retired incarnations")
        header = {key: value for key, value in body.items() if key != "wrapped"}
        context = canonical(header | dict(recipient=own))
        try:
            value = body["wrapped"][own]
            fields(value, ("ephemeral", "nonce", "ciphertext"))
            ephemeral = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(value["ephemeral"]))
            secret = AESGCM(_key(self.device.identity._key().exchange(ec.ECDH(), ephemeral), context)).decrypt(
                bytes.fromhex(value["nonce"]), bytes.fromhex(value["ciphertext"]), context)
            if len(secret) != 32:
                raise ValueError
        except (ValueError, TypeError, KeyError, InvalidTag) as error:
            raise JournalError("Invalid individual transport-key wrap") from error
        with self.db.transaction():
            self._save(dict(version=body["version"], epoch=body["epoch"], members=body["members"], retired=retired), secret)
            self.db.execute("INSERT OR REPLACE INTO journal_local VALUES(?,?)",("membership_wire:" + str(body["version"]),wire.decode()))
