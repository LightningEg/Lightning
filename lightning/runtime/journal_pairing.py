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
from lightning.sync.journal.pairing import PairingDesk, complete_number_match, number_choices, require_live_offer, prove_pairing, request_pairing


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
                    digits=digits,
                    confirmed=bool(state.get("confirmed")), number_match=bool(state and unpack(state["offer"].encode())["body"].get("method") == "number-match"),
                    choices=client.get("choices", []), failed=client.get("failed", False),
                    members=[names.get(identifier,"Paired device") for identifier in self.membership.state()["members"]
                             if identifier != self.device.identity.device_id],
                    member_details=[dict(id=identifier, name=names.get(identifier, "Paired device"))
                                    for identifier in self.membership.state()["members"]
                                    if identifier != self.device.identity.device_id],
                    nearby=[dict(id=identifier,name=value["name"], number_match=unpack(value["offer"].encode())["body"].get("method") == "number-match") for identifier,value in self._value("nearby",{}).items()],
                    pending=client.get("digits"), stage=client.get("stage"))

    def begin(self, password):
        if self.desk is None or self.keys is None:
            raise JournalError("Open pairing on the home")
        self.desk.begin(self.keys(),password,method="number-match")

    def stop(self):
        self.db.execute("DELETE FROM journal_local WHERE name='pairing'")

    def advertise(self, nonce, port):
        state = self._value("pairing",{})
        if not state or state["attempts"] >= 3 or state["proof_attempts"] >= 3 or unpack(state["offer"].encode())["body"]["expires"] <= time.time():
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
        secret = os.urandom(32) if offer.get("method") == "number-match" else None
        wire,digits = request_pairing(candidate["offer"].encode(),code,self.device.identity,config["incarnation"],home_key=offer["home_key"],secret=secret)
        request = self.client_factory(candidate["endpoint"],candidate["certificate"],timeout=5)
        answer = unpack(await request(wire))
        authenticate(answer,config["home_key"])
        if secret is not None:
            digits = await complete_number_match(candidate["offer"].encode(),wire,answer,secret,self.device.identity,request)
        elif answer["body"] != dict(type="pairing-wait",request=digest(unpack(wire)["body"])):
            raise JournalError("Pairing reply changed; reopen pairing on the home")
        with self.db.transaction():
            self._save("pairing_client",dict(candidate=candidate,request=wire.decode(),digits=digits,choices=number_choices(digits),stage="compare"))

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
        state = self._client("password")
        candidate = state["candidate"]
        offer = unpack(candidate["offer"].encode())["body"]
        wire = prove_pairing(candidate["offer"].encode(),state["request"].encode(),password,self.device.identity,home_key=offer["home_key"])
        answer = unpack(await self.client_factory(candidate["endpoint"],candidate["certificate"],timeout=5)(wire))
        authenticate(answer,self.device.store.config["home_key"])
        if answer["body"] != dict(type="pairing-wait",request=digest(unpack(state["request"].encode())["body"])):
            raise JournalError("Pairing reply changed; reopen pairing on the home")
        state["stage"] = "waiting"
        with self.db.transaction():
            self._save("pairing_client",state)

    def cancel(self):
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
        self._save("pairing_result:" + digest(request), dict(request=wire,membership=membership.decode(),expires=int(time.time())+600))
        names = self._value("paired_names",{})
        names[request["device"]] = request["name"]
        self._save("paired_names",names)

    def confirm(self, digits):
        state = self._value("pairing",{})
        if self.desk is None or not state.get("request"):
            raise JournalError("No device is waiting for approval")
        self.desk.confirm(digits)

    def exchange(self, wire):
        if self.desk is None or len(wire) > 4096:
            raise JournalError("Pairing request refused")
        envelope = unpack(wire)
        body = envelope["body"]
        if type(body) is not dict:
            raise JournalError("Invalid pairing message")
        if body.get("type") == "journal-pairing-request":
            self.desk.accept(wire)
            return seal(self.desk.waiting(),self.device.identity.sign)
        if body.get("type") == "journal-pairing-reveal":
            return self.desk.reveal(wire)
        if body.get("type") == "journal-pairing-proof":
            self.desk.prove(wire)
            return seal(dict(type="pairing-wait",request=body["request"]),self.device.identity.sign)
        fields(body,("type","request","device"))
        hash_value(body["request"])
        uuid(body["device"])
        saved = self._value("pairing_result:" + body["request"],{})
        if body["type"] != "journal-pairing-status" or not saved or saved["expires"] < time.time():
            raise JournalError("Pairing approval is not available yet")
        original = unpack(saved["request"].encode())["body"]
        authenticate(envelope,original["key"])
        if body["device"] != original["device"]:
            raise JournalError("Pairing approval belongs to another device")
        return seal(dict(type="pairing-approved",request=body["request"],membership=saved["membership"]),self.device.identity.sign)

    async def finish(self):
        state = self._value("pairing_client",{})
        if not state:
            raise JournalError("Choose a nearby device and enter its number first")
        if state["stage"] != "waiting":
            raise JournalError("Compare the numbers and enter your password first")
        identifier = digest(unpack(state["request"].encode())["body"])
        wire = seal(dict(type="journal-pairing-status",request=identifier,device=self.device.identity.device_id),self.device.identity.sign)
        candidate = state["candidate"]
        request = self.client_factory(candidate["endpoint"],candidate["certificate"],timeout=5)
        answer = unpack(await request(wire))
        authenticate(answer,self.device.store.config["home_key"])
        if answer["body"].get("type") != "pairing-approved" or answer["body"].get("request") != identifier:
            raise JournalError("Home has not approved this connection")
        with self.db.transaction():
            self.membership.accept(answer["body"]["membership"].encode(),initial=True)
            self._save("local_endpoints",[candidate["endpoint"].replace('/pairing/exchange','/exchange')])
            names = self._value("paired_names",{})
            names[candidate["home"]] = candidate["name"]
            self._save("paired_names",names)
            self.db.execute("DELETE FROM journal_local WHERE name='pairing_client'")
