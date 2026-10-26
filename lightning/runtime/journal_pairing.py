"""Nearby-device pairing flow for explicit compatible dummy profiles.

User-visible choices use names and opaque candidate IDs, never typed endpoints.
Native first-profile snapshot enrollment remains a separate cutover gate.
"""
from __future__ import annotations

import hmac
import json
import os
import time

from lightning.sync.journal.codec import JournalError, authenticate, canonical, digest, fields, hash_value, seal, unpack, uuid
from lightning.sync.journal.discovery import nearby_devices
from lightning.sync.journal.local import PinnedLocalClient
from lightning.sync.journal.membership import Membership
from lightning.sync.journal.pairing import PairingDesk, RECEIPT_LIFETIME, approval_receipt, number_choices, require_live_offer
from lightning.sync.journal import pairing_client


class NearbyPairing:
    def __init__(self, device, *, key_document=None, owner_document=None, search=nearby_devices, client_factory=PinnedLocalClient):
        self.device, self.db = device, device.store.db
        self.membership = Membership(device)
        self.keys, self.search, self.client_factory = key_document, search, client_factory
        self.desk = PairingDesk(device,self.membership,on_admit=self._admitted) if device.home else None
        from lightning.sync.journal.enrollment import EnrollmentSource
        self.enrollment = EnrollmentSource(device,key_document=key_document,owner_document=owner_document,
            approval=lambda identifier:self._value("pairing_result:"+identifier,{})) if device.home and key_document else None

    def _value(self, name, default=None):
        value = self.db.scalar("SELECT value FROM journal_local WHERE name=?", (name,))
        return json.loads(value) if value else default

    def _save(self, name, value):
        self.db.execute("INSERT OR REPLACE INTO journal_local VALUES(?,?)", (name,json.dumps(value,separators=(",",":"))))

    def screen(self):
        names = self._value("paired_names",{})
        state = self._value("pairing",{})
        if state and self.desk:
            state, _ = self.desk._state()
        if state and unpack(state["offer"].encode())["body"]["expires"] <= time.time():
            state = {}
        request = unpack(state["request"].encode())["body"] if state.get("request") else None
        digits = self.desk.digits(state, unpack(state["offer"].encode())["body"]) if request else None
        client = self._value("pairing_client",{})
        if client.get("stage") == "compare" and not client.get("choices"):
            client["choices"] = number_choices(client["digits"])
            with self.db.transaction():
                self._save("pairing_client",client)
        return dict(enabled=True, paired=self.device.identity.device_id in self.membership.state()["members"], code=state.get("code"), request_name=request["name"] if digits else None,
                    digits=digits, request_id=digest(request) if request else None,
                    confirmed=bool(state.get("confirmed")), number_match=bool(state and unpack(state["offer"].encode())["body"].get("method") == "number-match"),
                    choices=client.get("choices", []), failed=client.get("failed", False),
                    members=[names.get(identifier,"Paired device") for identifier in self.membership.state()["members"]
                             if identifier != self.device.identity.device_id],
                    member_details=[dict(id=identifier, name=names.get(identifier, "Paired device"))
                                    for identifier in self.membership.state()["members"]
                                    if identifier != self.device.identity.device_id],
                    nearby=[dict(id=identifier,name=value["name"], number_match=unpack(value["offer"].encode())["body"].get("method") == "number-match") for identifier,value in self._value("nearby",{}).items()],
                    pending=client.get("digits") or ("…" if client else None), stage=client.get("stage"))

    def begin(self, password):
        if self.desk is None or self.keys is None:
            raise JournalError("Open pairing on the home")
        self.desk.begin(self.keys(),password,method="number-match")

    def stop(self):
        self.db.execute("DELETE FROM journal_local WHERE name='pairing'")

    def advertise(self, nonce, port):
        state = self._value("pairing",{})
        if not state or state["attempts"] >= 12 or state["proof_attempts"] >= 3 or unpack(state["offer"].encode())["body"]["expires"] <= time.time():
            return None
        return seal(dict(type="journal-nearby-home", nonce=nonce, name=self.device.identity.name,
                         home=self.device.identity.device_id, offer=state["offer"], port=port,
                         certificate=self.device.identity.cert_path.read_text()),self.device.identity.sign)

    async def find(self):
        found = await self.search(self.device.identity)
        # Discovery advertises identity only. Matching digits, home approval and
        # password proof are required before any new device is admitted.
        candidates = {digest(dict(home=item["home"],offer=item["offer"])):item for item in found}
        with self.db.transaction():
            self._save("nearby",candidates)
        return len(candidates)

    async def join(self, identifier, code=""):
        candidate = self._value("nearby",{}).get(identifier)
        if candidate is None:
            raise JournalError("Search for nearby devices again")
        offer = unpack(candidate["offer"].encode())["body"]
        config = self.device.store.config
        from lightning.sync.journal.owner import public_key
        from types import SimpleNamespace
        if (offer["profile"] != config["profile"] or offer["generation"] != config["generation"]
                or public_key(SimpleNamespace(public_key=offer["home_key"])) != public_key(SimpleNamespace(public_key=config["home_key"]))):
            raise JournalError("This preview joins compatible dummy replicas; a new profile requires snapshot enrollment")
        if self.device.store.pending():
            raise JournalError("Sync existing pending work before pairing another connection")
        state = pairing_client.begin(candidate,self.device.identity,config["incarnation"],code)
        self._save_client(state)
        await self.resume()

    def _save_client(self, state):
        with self.db.transaction():
            self._save("pairing_client",state)

    def _client_state(self):
        state = self._value("pairing_client",{})
        if not state:
            raise JournalError("Choose a nearby device first")
        # Migrate already saved comparisons from the preceding application.
        if "wire" not in state:
            state["wire"] = state["request"]
            state["request"] = digest(unpack(state["wire"].encode())["body"])
            state["home_key"] = unpack(state["candidate"]["offer"].encode())["body"]["home_key"]
            self._save_client(state)
        return state

    def _exchange(self, state):
        candidate = state["candidate"]
        return self.client_factory(candidate["endpoint"],candidate["certificate"],timeout=5)

    async def resume(self):
        state = self._client_state()
        if state["stage"] == "handshake":
            await pairing_client.handshake(state,self.device.identity,self._exchange(state),self._save_client)
        elif state["stage"] == "proving":
            await pairing_client.status(state,self.device.identity,self._exchange(state),self._save_client)
        elif state["stage"] == "cancelling":
            await self.cancel()

    def _client(self, stage):
        state = self._value("pairing_client",{})
        if not state:
            raise JournalError("Choose a nearby device and enter its number first")
        if state.get("failed"):
            raise JournalError("Compare the numbers again: cancel and start a new pairing")
        require_live_offer(state["candidate"])
        if state["stage"] != stage:
            raise JournalError("Compare the numbers with the home first" if stage == "password" else "This step is already done")
        return state

    def compare(self, digits):
        """The joining user's confirmation that the home shows the same digits. Nothing leaves the device here."""
        state = self._client("compare")
        if type(digits) is not str or not hmac.compare_digest(digits, state["digits"]):
            state["failed"] = True
            with self.db.transaction():
                self._save("pairing_client", state)
            raise JournalError("Check that both devices show the same six digits")
        state["stage"] = "password"
        with self.db.transaction():
            self._save("pairing_client",state)

    async def prove(self, password):
        state = self._client_state()
        await pairing_client.prove(state,self.device.identity,password,self._exchange(state),self._save_client)

    async def cancel(self):
        if not self._value("pairing_client",{}):
            return
        state = self._client_state()
        await pairing_client.cancel(state,self.device.identity,self._exchange(state),self._save_client)
        self.db.execute("DELETE FROM journal_local WHERE name='pairing_client'")

    def revoke(self, identifier):
        if self.device.home is None:
            raise JournalError("Remove paired devices on the current home")
        members = dict(self.membership.state()["members"])
        if identifier == self.device.identity.device_id or identifier not in members:
            raise JournalError("Choose a paired device other than this home")
        del members[identifier]
        with self.device.store.confirming():
            self.membership.rotate(members)

    def _admitted(self, wire, membership):
        request = unpack(wire.encode())["body"]
        self._save("pairing_result:" + digest(request), dict(request=wire,membership=membership.decode(),expires=int(time.time())+RECEIPT_LIFETIME))
        names = self._value("paired_names",{})
        names[request["device"]] = request["name"]
        self._save("paired_names",names)

    def confirm(self, digits, request_id=None):
        state = self._value("pairing",{})
        if self.desk is None or not state.get("request"):
            raise JournalError("No device is waiting for approval")
        self.desk.confirm(digits, request_id=request_id)

    def exchange(self, wire):
        if self.desk is None or len(wire) > 4096:
            raise JournalError("Pairing request refused")
        envelope = unpack(wire)
        body = envelope["body"]
        if type(body) is not dict:
            raise JournalError("Invalid pairing message")
        kind = body.get("type")
        identifier = digest(body) if kind == "journal-pairing-request" else body.get("request")
        if identifier is not None:
            hash_value(identifier)
        saved = self._value("pairing_result:"+identifier,{}) if identifier else {}
        if kind == "journal-pairing-cancel":
            # A revoked/expired receipt must not strand a local cancellation.
            # The desk verifies the original signed offer/request and refuses
            # cancellation while the identity is still approved.
            return self.desk.cancel(wire)
        if saved:
            original = approval_receipt(self.device,saved)
            authenticate(envelope,original["key"])
            if ((body.get("device") != original["device"]) or (kind == "journal-pairing-request" and body != original)
                    or (kind in {"journal-pairing-proof","journal-pairing-cancel"} and body.get("offer") != original["offer"])
                    or kind not in {"journal-pairing-request","journal-pairing-proof","journal-pairing-status","journal-pairing-cancel"}):
                raise JournalError("Pairing approval belongs to another request")
            answer = dict(type="pairing-approved",request=identifier,membership=saved["membership"])
            if kind == "journal-pairing-status" and "nonce" in body:
                hash_value(body["nonce"])
                answer["nonce"] = body["nonce"]
            return seal(answer,self.device.identity.sign)
        if kind == "journal-pairing-request":
            self.desk.accept(wire)
            return seal(self.desk.waiting(),self.device.identity.sign)
        if kind == "journal-pairing-reveal":
            return self.desk.reveal(wire)
        if kind == "journal-pairing-cancel":
            return self.desk.cancel(wire)
        if kind == "journal-pairing-proof":
            self.desk.prove(wire)
            return seal(dict(type="pairing-wait",request=body["request"]),self.device.identity.sign)
        fields(body,("type","request","device") + (("nonce",) if "nonce" in body else ()))
        if "nonce" in body:
            hash_value(body["nonce"])
        uuid(body["device"])
        state, offer = self.desk._state()
        if kind != "journal-pairing-status" or not state.get("request") or self.desk.clock() >= offer["expires"]:
            raise JournalError("Pairing approval is not available yet")
        original = unpack(state["request"].encode())["body"]
        authenticate(envelope,original["key"])
        if body["request"] != digest(original) or body["device"] != original["device"]:
            raise JournalError("Pairing approval belongs to another device")
        answer = dict(type="pairing-pending",request=body["request"],proof=bool(state["proof"] or state.get("queued_proof")))
        if "nonce" in body:
            answer["nonce"] = body["nonce"]
        return seal(answer,self.device.identity.sign)

    async def finish(self):
        state = self._client_state()
        if state["stage"] not in ("waiting","proving"):
            raise JournalError("Compare the numbers and enter your password first")
        answer = await pairing_client.status(state,self.device.identity,self._exchange(state),self._save_client)
        if answer["type"] != "pairing-approved":
            raise JournalError("Pairing approval is not available yet")
        candidate = state["candidate"]
        with self.db.transaction():
            self.membership.accept(answer["membership"].encode(),initial=True)
            self._save("local_endpoints",[candidate["endpoint"].replace('/pairing/exchange','/exchange')])
            names = self._value("paired_names",{})
            names[candidate["home"]] = candidate["name"]
            self._save("paired_names",names)
            self.db.execute("DELETE FROM journal_local WHERE name='pairing_client'")
