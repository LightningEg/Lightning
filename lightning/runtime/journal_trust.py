"""Owner-authorized journal trust changes for the unlocked native profile."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from lightning.runtime.session import AttemptGuard, read_slot, write_slot
from lightning.sync.journal.authority import AuthorityRegistry
from lightning.sync.journal.codec import JournalError, seal
from lightning.sync.journal.owner import OwnerCredential


class JournalTrustRuntime:
    """Rotate owner credentials and invoke verified home recovery or handoff."""

    def __init__(self, device, pairing, paths, owner_document, *, owner_path=None, internet=None,
                 save_owner_document=None, move_runtime=None):
        self.device, self.pairing, self.paths = device, pairing, paths
        self.owner_document = owner_document
        self.owner_path = Path(owner_path) if owner_path else None
        self.internet, self.save_owner_document = internet, save_owner_document
        self.move_runtime = move_runtime

    def state(self):
        memory = self.device.store.authority
        if memory is None:
            return dict(available=False, phase="unavailable", reason="Owner authority is not enrolled")
        authority = memory.state()
        return dict(available=True, phase=authority["phase"], mode=authority.get("mode"),
                    generation=authority["generation"], version=authority["version"],
                    can_rotate_owner=authority["phase"] == "active" and self.device.home is not None,
                    can_recover_home=(authority["phase"] in {"active", "retired", "candidate"}
                                      and self.device.store.config["role"] == "replica" and self.internet is not None
                                      and getattr(self.internet, "configured", True)),
                    can_move_home=(self.device.home is None and self.move_runtime is not None),
                    targets=[])

    def _guard(self):
        profile = self.device.store.config["profile"]
        directory = self.owner_path.parent if self.owner_path else Path(self.device.store.db.path).parent
        return AttemptGuard(directory / f".journal-owner-attempts-{profile}.json")

    def _read_owner(self):
        if self.owner_path is not None:
            return read_slot(self.owner_path)
        value = self.owner_document() if callable(self.owner_document) else self.owner_document
        if not isinstance(value, dict):
            raise JournalError("Owner recovery material is unavailable")
        return value

    def _owner_credential(self, proofs):
        """Unlock the owner signer with the same throttled verifier used by recovery."""
        owner = OwnerCredential.unlock(self._read_owner(), proofs, guard=self._guard())
        state = self.device.store.authority.state()
        if owner.public_key != state["owner_key"]:
            raise JournalError("Owner credentials do not match the pinned authority")
        return owner

    def _save_owner(self, document):
        if self.save_owner_document is not None:
            self.save_owner_document(document)
            return
        if self.owner_path is None:
            raise JournalError("Owner credential storage is unavailable")
        write_slot(self.owner_path, document, replace=True)

    def rotate_owner(self, *, password, answer, recovery, new_password, new_answer, new_recovery):
        """Rotate the independently wrapped owner signing key after two current proofs."""
        device, store = self.device, self.device.store
        memory = store.authority
        if memory is None or device.home is None:
            raise JournalError("Only the active home can rotate owner credentials")
        current = memory.state()
        profile = store.config["profile"]
        directory = self.owner_path.parent if self.owner_path else Path(store.db.path).parent
        intent_path = directory / f".journal-owner-rotation-{profile}.json"
        proofs = dict(password=password, answer=answer) if password and answer else (
            dict(password=password, recovery=recovery) if password and recovery else
            dict(answer=answer, recovery=recovery) if answer and recovery else {})
        if len(proofs) != 2:
            raise JournalError("Enter any two current owner credentials")
        from lightning.sync.journal.codec import unpack
        if intent_path.exists() or intent_path.is_symlink():
            if intent_path.is_symlink():
                raise JournalError("Owner rotation evidence is unsafe; preserve it for repair")
            intent = read_slot(intent_path)
            if set(intent) != {"profile", "previous", "generation", "wire", "document"} or intent["profile"] != profile:
                raise JournalError("Owner rotation evidence is malformed; preserve it for repair")
            successor = OwnerCredential.unlock(intent["document"], self._new_proofs(new_password, new_answer, new_recovery), guard=self._guard())
            body = unpack(intent["wire"].encode())["body"]
            if body["generation"] != intent["generation"] or body["previous"] != intent["previous"] or body["owner_key"] != successor.public_key:
                raise JournalError("Owner rotation evidence does not match the new credentials")
            if current["generation"] != intent["previous"]:
                memory.verify_transition(intent["wire"].encode(), allow_observed=True)
            if current["generation"] == intent["previous"] and current["phase"] == "active":
                owner = OwnerCredential.unlock(self._read_owner(), proofs, guard=self._guard())
                memory.verify_transition(intent["wire"].encode())
                if not memory.can_confirm(store) or owner.public_key != current["owner_key"]:
                    raise JournalError("Current owner credentials do not match authority")
                memory.observe(intent["wire"].encode(), local_device=store.config["device"])
                current = memory.state()
            if current["generation"] == intent["generation"] and current["phase"] == "candidate":
                memory._activate(store, body, home_signer=device.identity.sign)
                current = memory.state()
            if current["generation"] != intent["generation"] or current["phase"] != "active":
                raise JournalError("Owner rotation is not at a resumable authority phase")
            self._save_owner(intent["document"])
            intent_path.unlink()
            self._sync_directory(directory)
        else:
            if current["phase"] != "active" or not memory.can_confirm(store):
                raise JournalError("Owner authority is not active on this home")
            owner = OwnerCredential.unlock(self._read_owner(), proofs, guard=self._guard())
            if owner.public_key != current["owner_key"]:
                raise JournalError("Current owner credentials do not match authority")
            successor, document = OwnerCredential.create(profile, password=new_password,
                                                           recovery=new_recovery, answer=new_answer)
            generation = str(uuid4())
            body = dict(profile=profile, previous=current["generation"], generation=generation,
                        home=store.config["device"], home_key=store.config["home_key"],
                        owner_key=successor.public_key, version=current["version"] + 1,
                        mode="rotate-owner", nonce=os.urandom(32).hex(), cutoff=store.cursor())
            wire = seal(body, owner.sign)
            write_slot(intent_path, dict(profile=profile, previous=current["generation"], generation=generation,
                                         wire=wire.decode(), document=document))
            memory.observe(wire, local_device=store.config["device"])
            memory._activate(store, body, home_signer=device.identity.sign)
            self._save_owner(document)
            intent_path.unlink()
            self._sync_directory(directory)
        return "Owner credentials rotated. Paired devices must reconnect to the new generation."

    @staticmethod
    def _new_proofs(password, answer, recovery):
        if password and answer:
            return dict(password=password, answer=answer)
        if password and recovery:
            return dict(password=password, recovery=recovery)
        if answer and recovery:
            return dict(answer=answer, recovery=recovery)
        raise JournalError("Enter any two new owner credentials")

    @staticmethod
    def _sync_directory(directory):
        if os.name != "nt":
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    async def recover_home(self, *, password, answer, recovery=""):
        """Claim the verified surviving replica after the registry accepts recovery."""
        from lightning.sync.journal.home import JournalHome
        from lightning.sync.journal.membership import Membership
        from lightning.sync.journal.cloud import CloudUnavailable
        from lightning.sync.journal.codec import unpack

        device, store = self.device, self.device.store
        memory = store.authority
        if (memory is None or self.internet is None or not getattr(self.internet, "configured", True)
                or getattr(getattr(self.internet, "peer", None), "client", None) is None):
            raise CloudUnavailable("Reconnect to the authority registry before recovering the home")
        current = memory.state()
        if current["phase"] not in {"active", "retired", "candidate"}:
            raise JournalError("This copy is not ready to recover the home")
        proofs = dict(password=password, answer=answer) if password and answer else (
            dict(password=password, recovery=recovery) if password and recovery else
            dict(answer=answer, recovery=recovery) if answer and recovery else {})
        if len(proofs) != 2:
            raise JournalError("Enter any two owner credentials")
        owner = OwnerCredential.unlock(self._read_owner(), proofs, guard=self._guard())
        if owner.public_key != current["owner_key"]:
            raise JournalError("Owner credentials do not match the pinned authority")
        profile = store.config["profile"]
        directory = self.owner_path.parent if self.owner_path else Path(store.db.path).parent
        intent_path = directory / f".journal-home-recovery-{profile}.json"
        if intent_path.is_symlink():
            raise JournalError("Recovery intent is unsafe; preserve it for repair")
        if intent_path.exists():
            intent = read_slot(intent_path)
            if set(intent) != {"profile", "wire"} or intent["profile"] != profile or type(intent["wire"]) is not str:
                raise JournalError("Recovery intent is malformed; preserve it for repair")
            wire = intent["wire"].encode()
            body = unpack(wire)["body"]
            if (body.get("mode") != "recover" or body.get("profile") != profile
                    or body.get("home") != store.config["device"]
                    or body.get("home_key") != device.identity.public_key
                    or body.get("owner_key") != owner.public_key):
                raise JournalError("Saved recovery intent does not match this owner or device")
            if current["generation"] == body.get("previous"):
                if (body.get("version") != current["version"] + 1 or body.get("cutoff") != store.cursor()
                        or current["phase"] != "active"):
                    raise JournalError("Saved recovery intent no longer matches the surviving checkpoint")
                memory.verify_transition(wire)
            elif current["generation"] == body.get("generation"):
                memory.verify_transition(wire, allow_observed=True)
                if current["phase"] not in {"candidate", "active"}:
                    raise JournalError("Saved recovery intent is not a local successor")
            else:
                raise JournalError("A competing authority was observed; preserve the recovery intent")
        else:
            if current["phase"] != "active":
                raise JournalError("Only the surviving active checkpoint can start recovery")
            body = dict(profile=profile, previous=current["generation"], generation=str(uuid4()),
                        home=store.config["device"], home_key=device.identity.public_key,
                        owner_key=owner.public_key, version=current["version"] + 1, mode="recover",
                        nonce=os.urandom(32).hex(), cutoff=store.cursor())
            wire = seal(body, owner.sign)
            write_slot(intent_path, dict(profile=profile, wire=wire.decode()))
        await memory.recover(store, wire, AuthorityRegistry(self.internet.peer.client), home_signer=device.identity.sign)
        state = memory.state()
        if state["generation"] != body["generation"] or state["phase"] != "active":
            raise JournalError("The authority registry accepted recovery but local activation is incomplete")
        device.home = JournalHome(store, device.identity.sign)
        membership = Membership(device).state()
        for identifier, member in membership["members"].items():
            device.home.approve_origin(identifier, member["incarnation"], member["key"])
        device.flush_home()
        intent_path.unlink(missing_ok=True)
        self._sync_directory(directory)
        return "The registry accepted the surviving checkpoint as the new home. Paired devices can reconnect."

    async def move_home(self, *, target="", password, **proofs):
        """Run the signed target-initiated checkpoint and retirement protocol."""
        if self.move_runtime is None:
            raise JournalError("The local authority exchange service is unavailable")
        return await self.move_runtime.move_home(password=password, **proofs)
