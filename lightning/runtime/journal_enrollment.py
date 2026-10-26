"""First-replica pairing and resumable enrollment for the journal runtime.

No password or decrypted profile key is stored in the enrollment state. The
native picker must publish a completed directory before offering it as a profile.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from uuid import uuid4

from lightning.security.keys import unwrap_key
from lightning.sync.identity import load_or_create
from lightning.sync.journal.cloud import CheckpointTransfer
from lightning.sync.journal.codec import JournalError, authenticate, digest, seal, unpack
from lightning.sync.journal.discovery import nearby_devices
from lightning.sync.journal.enrollment import install_replica
from lightning.sync.journal.local import PinnedLocalClient
from lightning.sync.journal.pairing import number_choices, require_live_offer
from lightning.sync.journal import pairing_client
from .session import read_slot, write_slot


class NewJournalReplica:
    def __init__(self, root, name, *, search=nearby_devices, client_factory=PinnedLocalClient):
        self.root = Path(root)
        if self.root.is_symlink():
            raise JournalError("Invalid enrollment directory")
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        marker = self.root/"journal-enrollment-root.json"
        if not marker.exists():
            if any(self.root.iterdir()):
                raise JournalError("Use an empty private directory for first enrollment")
            write_slot(marker,dict(format=1))
        elif marker.is_symlink() or read_slot(marker) != dict(format=1):
            raise JournalError("Invalid enrollment directory marker")
        if (self.root/"enrollment.json").exists():
            for filename in ("device.json","device-key.pem","device-cert.pem"):
                path = self.root/"identity"/filename
                if path.is_symlink() or not path.is_file():
                    raise JournalError("The enrolled identity is missing; preserve this directory for repair")
        self.identity = load_or_create(self.root/"identity",name)
        self.search,self.client_factory = search,client_factory
        self.candidates = {}

    def state(self):
        path = self.root/"enrollment.json"
        state = read_slot(path) if path.exists() else None
        if state is not None and state.get("stage") == "compare" and not state.get("choices"):
            state["choices"] = number_choices(state["digits"])
            write_slot(path,state,replace=True)
        return state

    async def find(self):
        self.candidates = {digest(dict(home=item["home"],offer=item["offer"])):item for item in await self.search(self.identity)}
        return [dict(id=identifier,name=item["name"], number_match=unpack(item["offer"].encode())["body"].get("method") == "number-match") for identifier,item in self.candidates.items()]

    async def join(self, candidate_id, code=""):
        if self.state() is not None or (self.root/"ledger.db").exists():
            raise JournalError("Resume the existing pairing instead of pairing again")
        candidate = self.candidates.get(candidate_id)
        if candidate is None:
            raise JournalError("Find the nearby device again")
        offer = unpack(candidate["offer"].encode())["body"]
        state = pairing_client.begin(candidate,self.identity,str(uuid4()),code)
        self._save_pairing(state)
        await self.resume()
        return self.state()["digits"]

    def _save_pairing(self, state):
        write_slot(self.root/"enrollment.json",state,replace=(self.root/"enrollment.json").exists())

    def _pairing_exchange(self, state):
        candidate = state["candidate"]
        return self.client_factory(candidate["endpoint"],candidate["certificate"],timeout=5)

    async def resume(self):
        state = self.state()
        if state is None:
            raise JournalError("Find a nearby device first")
        if state["stage"] == "handshake":
            await pairing_client.handshake(state,self.identity,self._pairing_exchange(state),self._save_pairing)
        elif state["stage"] in ("proving","waiting"):
            await pairing_client.status(state,self.identity,self._pairing_exchange(state),self._save_pairing)
        elif state["stage"] == "cancelling":
            await self.cancel()

    def compare(self, digits):
        """The joining user's confirmation that the home shows the same digits. Nothing leaves the device here."""
        state = self.state()
        if state is None or state.get("stage") != "compare":
            raise JournalError("Find a home and enter its number first")
        require_live_offer(state["candidate"])
        if state.get("failed"):
            raise JournalError("Compare the numbers again: cancel and start a new pairing")
        if type(digits) is not str or not hmac.compare_digest(digits,state["digits"]):
            write_slot(self.root/"enrollment.json",dict(state,failed=True),replace=True)
            raise JournalError("Check that both devices show the same six digits")
        write_slot(self.root/"enrollment.json",dict(state,stage="password"),replace=True)

    async def prove(self, password):
        state = self.state()
        if state is None:
            raise JournalError("Compare the numbers with the home first")
        await pairing_client.prove(state,self.identity,password,self._pairing_exchange(state),self._save_pairing)

    async def cancel(self):
        state = self.state()
        if state is None:
            return
        if (self.root/"ledger.db").exists() or (self.root/"install-intent.json").exists():
            raise JournalError("Resume the encrypted copy installation before cancelling")
        await pairing_client.cancel(state,self.identity,self._pairing_exchange(state),self._save_pairing)
        (self.root/"enrollment.json").unlink()

    async def finish(self, password, *, budget=50):
        state = self.state()
        if state is None:
            raise JournalError("Find a home and enter its number first")
        if state.get("stage") == "proving":
            await pairing_client.status(state,self.identity,self._pairing_exchange(state),self._save_pairing)
        if state.get("stage","waiting") != "waiting":
            raise JournalError("Compare the numbers and enter your password first")
        if (self.root/"complete.json").exists():
            complete = read_slot(self.root/"complete.json")
            if any(complete.get(name) != value for name,value in dict(profile=state["profile"],generation=state["generation"],device=self.identity.device_id).items()):
                raise JournalError("Enrollment completion marker differs; preserve this directory")
            unwrap_key(read_slot(self.root/"keys.json"),password)
            return True
        intent_path = self.root/"install-intent.json"
        if intent_path.exists():
            metadata = read_slot(intent_path)["metadata"]
            identifier = hashlib.sha256(metadata["manifest"].encode()).hexdigest()
            return self._publish(state,metadata,self.root/"chunks"/(identifier+".db"),password)
        candidate = state["candidate"]
        request = self.client_factory(candidate["endpoint"].replace('/pairing/exchange','/enrollment/exchange'),candidate["certificate"],timeout=5)
        async def exchange(operation,index=0):
            nonce = os.urandom(32).hex()
            wire = seal(dict(type="journal-enrollment",profile=state["profile"],generation=state["generation"],
                             sender=self.identity.device_id,request=state["request"],operation=operation,index=index,nonce=nonce),self.identity.sign)
            response = unpack(await request(wire))
            authenticate(response,state["home_key"])
            body = response["body"]
            if set(body) != {"type","nonce","request","result"} or body["type"] != "journal-enrollment-reply" or body["nonce"] != nonce or body["request"] != state["request"]:
                raise JournalError("Enrollment response belongs to another request")
            return body["result"]
        metadata = await exchange("metadata")
        certificates = []
        for _ in range(16):
            if len(certificates) == metadata["authority_version"]:
                break
            page = await exchange("authority",len(certificates))
            if not page["certificates"] or len(page["certificates"]) > 8 or page["latest"] != metadata["authority_version"]:
                raise JournalError("Authority changed during enrollment; retry from its verified checkpoint")
            certificates.extend(page["certificates"])
        if len(certificates) != metadata["authority_version"]:
            raise JournalError("Authority enrollment history limit exceeded")
        metadata["certificates"] = certificates
        manifest = metadata["manifest"].encode()
        unwrap_key(metadata["keys"],password)
        class Chunks:
            async def call(self,route,data):
                if route != "/snapshot/get" or data["id"] != hashlib.sha256(manifest).hexdigest():
                    raise JournalError("Invalid enrollment chunk request")
                result = await exchange("chunk",data["index"])
                if result["index"] != data["index"]:
                    raise JournalError("Enrollment chunk index mismatch")
                from lightning.sync.journal.local import decode
                import base64
                return dict(bytes=base64.b64encode(decode(result["data"])).decode(),sha256=result["sha256"])
        transfer = CheckpointTransfer(Chunks(),self.root/"chunks")
        source = await transfer.download(manifest,public_key=state["home_key"],budget=budget)
        if source is None:
            return False
        return self._publish(state,metadata,source,password)

    def _publish(self,state,metadata,source,password):
        target = self.root/"ledger.db"
        manifest = metadata["manifest"].encode()
        key = unwrap_key(metadata["keys"],password)
        intent = dict(manifest=hashlib.sha256(manifest).hexdigest(),incarnation=state["incarnation"],profile=state["profile"],metadata=metadata)
        intent_path = self.root/"install-intent.json"
        resume = intent_path.exists()
        if resume and read_slot(intent_path) != intent:
            raise JournalError("Enrollment installation intent differs; preserve this directory")
        if not resume:
            write_slot(intent_path,intent)
        authority = self._authority(state,metadata)
        if metadata.get("owner") is not None:
            write_slot(self.root/"owner-authority.json",metadata["owner"],replace=(self.root/"owner-authority.json").exists())
        write_slot(self.root/"keys.json",metadata["keys"],replace=(self.root/"keys.json").exists())
        install_replica(source,manifest,key=key,identity=self.identity,incarnation=state["incarnation"],membership=metadata["membership"].encode(),
                        home_key=state["home_key"],profile=state["profile"],generation=state["generation"],target=target,resume=resume)
        complete = dict(profile=state["profile"],generation=state["generation"],device=self.identity.device_id)
        if authority is not None:
            from lightning.database.connection import Database
            from lightning.sync.journal.store import JournalStore
            from lightning.sync.journal.authority import AuthorityMemory
            memory = AuthorityMemory(authority,profile=state["profile"])
            db = None
            try:
                db = Database(target,key=key)
                memory.bind(JournalStore(db))
            finally:
                if db is not None:
                    db.close()
                memory.close()
            complete["authority"] = str(authority)
        write_slot(self.root/"complete.json",complete)
        return True


    def _authority(self,state,metadata):
        from types import SimpleNamespace
        from lightning.sync.journal.authority import AuthorityMemory
        from lightning.sync.journal.owner import public_key
        certificates = metadata.get("certificates",[])
        if not certificates:
            if metadata.get("owner") is not None or metadata.get("authority_version",0) != 0:
                raise JournalError("Owner authority history is missing")
            return None
        if len(certificates) != metadata["authority_version"]:
            raise JournalError("Owner authority history is incomplete")
        folder = self.root.parent/".journal-authority"
        if folder.is_symlink():
            raise JournalError("Invalid independent authority directory")
        folder.mkdir(mode=0o700,exist_ok=True)
        path = folder/(state["profile"]+"."+self.identity.device_id+".db")
        memory = AuthorityMemory(path,profile=state["profile"]) if path.exists() else AuthorityMemory.enroll(path,certificates[0].encode())
        try:
            version = memory.state()["version"]
            if version > len(certificates):
                raise JournalError("Enrollment cannot rewind observed authority")
            for certificate in certificates[version:]:
                memory.observe(certificate.encode(),local_device=self.identity.device_id)
            current = memory.state()
            owner = metadata["owner"]
            if (current["generation"] != state["generation"] or current["profile"] != state["profile"]
                    or public_key(SimpleNamespace(public_key=current["home_key"])) != public_key(SimpleNamespace(public_key=state["home_key"]))
                    or owner is None or owner["profile"] != state["profile"] or owner["public_key"] != current["owner_key"]):
                raise JournalError("Enrollment authority differs from the approved home")
            result = memory.path
            memory.close()
            return result
        except BaseException:
            memory.close()
            raise
