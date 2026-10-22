"""Pinned, resumable LAN handoff of journal authority to an enrolled replica.

Every message is signed by its device identity and scoped to the current profile.
The home freezes before exposing checkpoint bytes, and retirement only follows a
target receipt over the verified final checkpoint.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from lightning.sync.journal.codec import JournalError, authenticate, canonical, digest, fields, hash_value, number, seal, unpack, uuid
from lightning.sync.journal.local import PinnedLocalClient, decode, encode
from lightning.sync.journal.membership import Membership
from lightning.runtime.session import read_slot, write_slot

MAX_WIRE = 4096
CHUNK_SIZE = 24 * 1024
MAX_CHECKPOINT = 200 * 1024 * 1024
TRANSFER_CHUNK = 9 * 1024
TABLES = ("journal_origins", "journal_inbox", "journal_reviews")


def _line(value):
    """Canonical local JSON framing allows large DB blobs split at transport level."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


class JournalMoveRuntime:
    """Server side of the old-home exchange and target-side move coordinator.

    Construct once per unlocked profile runtime. The profile TLS listener routes
    POST ``/authority/exchange`` bytes here; target initiation uses the previously
    pinned ``/exchange`` endpoint and certificate.
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self.device, self.store = runtime.device, runtime.device.store
        self.identity = runtime.identity
        self.memory = self.store.authority
        self.directory = Path(runtime.paths.data_dir) / ".journal-move"
        if self.directory.is_symlink():
            raise JournalError("The local move recovery folder is unsafe")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.directory.is_dir():
            raise JournalError("The local move recovery folder is unavailable")

    def _respond(self, request, result):
        body = unpack(request)["body"]
        return seal(dict(type="journal-move-reply", nonce=body["nonce"], result=result), self.identity.sign)

    def _authenticate_request(self, wire):
        if type(wire) is not bytes or len(wire) > MAX_WIRE:
            raise JournalError("Move request limit exceeded")
        envelope = unpack(wire)
        body = envelope["body"]
        fields(body, ("type", "profile", "generation", "sender", "incarnation", "operation", "nonce", "value"))
        for key in ("profile", "generation", "sender", "incarnation"):
            uuid(body[key])
        hash_value(body["nonce"])
        self.store._scope(body)
        member = Membership(self.device).state()["members"].get(body["sender"])
        if member is None or member["incarnation"] != body["incarnation"]:
            raise JournalError("Move sender is not an enrolled device")
        authenticate(envelope, member["key"])
        if body["type"] != "journal-move" or type(body["value"]) is not dict:
            raise JournalError("Invalid move request")
        return body

    def exchange(self, wire):
        """Handle a bounded signed request from an enrolled target device."""
        body = self._authenticate_request(wire)
        if self.memory is None or self.device.home is None:
            raise JournalError("Only an enrolled current home can serve a move")
        operation = body["operation"]
        if operation == "authorize":
            return self._respond(wire, self._authorize(body))
        state = self._load(body["sender"])
        if not state:
            raise JournalError("The current home has not authorized this move")
        if operation == "metadata":
            return self._respond(wire, dict(manifest=state["manifest"], cutoff=state["cutoff"],
                                            chunks=(state["size"] + CHUNK_SIZE - 1) // CHUNK_SIZE,
                                            transfer_chunks=state["transfer_chunks"],
                                            transfer_size=state["transfer_size"],
                                            transfer_hash=state["transfer_hash"],
                                            transfer_items=state["transfer_items"]))
        if operation == "chunk":
            index = body["value"].get("index")
            if type(index) is not int or index < 0 or index >= (state["size"] + CHUNK_SIZE - 1) // CHUNK_SIZE:
                raise JournalError("Invalid checkpoint chunk")
            path = self.directory / state["file"]
            if path.is_symlink() or not path.is_file() or path.stat().st_size != state["size"]:
                raise JournalError("The frozen checkpoint is missing; preserve the move record")
            with path.open("rb") as handle:
                handle.seek(index * CHUNK_SIZE)
                data = handle.read(CHUNK_SIZE)
            return self._respond(wire, dict(index=index, data=encode(data), sha256=hashlib.sha256(data).hexdigest()))
        if operation == "transfer":
            index = body["value"].get("index")
            if type(index) is not int or index < 0 or index >= state["transfer_chunks"]:
                raise JournalError("Invalid home-state chunk")
            path = self.directory / state["transfer_file"]
            if path.is_symlink() or not path.is_file() or path.stat().st_size != state["transfer_size"]:
                raise JournalError("The frozen home-state transfer is missing; preserve the move record")
            with path.open("rb") as handle:
                handle.seek(index * TRANSFER_CHUNK)
                data = handle.read(TRANSFER_CHUNK)
            return self._respond(wire, dict(index=index, data=encode(data), sha256=hashlib.sha256(data).hexdigest()))
        if operation == "retire":
            transition_wire, prepared = body["value"].get("transition"), body["value"].get("prepared")
            if type(transition_wire) is not str or type(prepared) is not str:
                raise JournalError("Invalid target preparation receipt")
            receipt = self.memory.retire(self.store, transition_wire.encode(), prepared.encode(), self.identity.sign)
            self._save(body["sender"], state | dict(retired=receipt.decode()))
            return self._respond(wire, dict(retired=receipt.decode()))
        raise JournalError("Unknown authority exchange operation")

    def _authorize(self, request):
        """Validate the target's independent owner-signed move intent, then freeze."""
        value = request["value"]
        fields(value, ("intent",))
        intent = unpack(value["intent"].encode())
        body = intent["body"]
        fields(body, ("type", "profile", "generation", "target", "target_key", "nonce"))
        for key in ("profile", "generation", "target"):
            uuid(body[key])
        hash_value(body["nonce"])
        current = self.memory.state()
        if (body["type"] != "journal-move-intent" or body["profile"] != current["profile"]
                or body["generation"] != current["generation"] or body["target"] != request["sender"]
                or request["sender"] not in Membership(self.device).state()["members"]):
            raise JournalError("Move intent differs from the current home or enrolled target")
        authenticate(intent, current["owner_key"])
        from lightning.sync.journal.owner import public_key
        from types import SimpleNamespace
        if public_key(SimpleNamespace(public_key=body["target_key"])) != public_key(SimpleNamespace(public_key=Membership(self.device).state()["members"][request["sender"]]["key"])):
            raise JournalError("Move target key differs from its enrolled identity")
        saved = self._load(request["sender"])
        if saved:
            if saved["intent"] != value["intent"]:
                raise JournalError("A competing move is already frozen")
            return dict(cutoff=saved["cutoff"])
        cutoff = self.memory.freeze(self.store)
        try:
            path = self.directory / (request["sender"] + ".db")
            if path.is_symlink():
                raise JournalError("The frozen checkpoint path is unsafe; preserve it for repair")
            path.unlink(missing_ok=True)
            from lightning.sync.journal.snapshots import export
            manifest = export(self.store, path, self.identity.sign)
            size = path.stat().st_size
            if not 0 < size <= MAX_CHECKPOINT:
                raise JournalError("Checkpoint exceeds the local handoff limit")
            transfer_path = self.directory / (request["sender"] + ".rows")
            transfer_size, transfer_hash, transfer_items = self._create_transfer(transfer_path)
            state = dict(intent=value["intent"], cutoff=cutoff, manifest=manifest.decode(),
                         file=path.name, size=size, transfer_file=transfer_path.name,
                         transfer_size=transfer_size, transfer_hash=transfer_hash, transfer_items=transfer_items,
                         transfer_chunks=(transfer_size + TRANSFER_CHUNK - 1) // TRANSFER_CHUNK, retired="")
            self._save(request["sender"], state)
            return dict(cutoff=cutoff)
        except BaseException:
            # Freeze is intentionally durable. It blocks confirmation until the same
            # owner-signed move resumes or explicit repair resolves it.
            raise

    def _create_transfer(self, target):
        """Persist line-framed authority rows; wire exchange fragments arbitrary-size rows."""
        import base64
        if target.is_symlink():
            raise JournalError("The home-state transfer path is unsafe")
        target.unlink(missing_ok=True)
        total, count = 0, 0
        hasher = hashlib.sha256()
        with target.open("xb") as handle:
            for table in TABLES:
                for row in self.store.db.all(f"SELECT * FROM {table} ORDER BY rowid"):
                    item = dict(table=table, values=[dict(bytes=base64.b64encode(row[key]).decode())
                                                     if isinstance(row[key], bytes) else dict(value=row[key])
                                                     for key in row.keys()])
                    wire = _line(item) + b"\n"
                    total += len(wire)
                    if total > MAX_CHECKPOINT:
                        raise JournalError("Home authority state exceeds the handoff limit")
                    handle.write(wire); hasher.update(wire); count += 1
            handle.flush(); os.fsync(handle.fileno())
        return total, hasher.hexdigest(), count

    def _load(self, target):
        path = self.directory / (target + ".state")
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise JournalError("Move recovery record is unsafe; preserve it for repair")
        return read_slot(path)

    def _save(self, target, value):
        path = self.directory / (target + ".state")
        write_slot(path, value, replace=path.exists())

    async def move_home(self, *, password, answer="", recovery=""):
        """Move this enrolled replica to home after two owner proofs and a full receipt chain."""
        if self.device.home is not None or self.memory is None:
            raise JournalError("Start a move only on an enrolled replica")
        if self.store.pending():
            raise JournalError("Sync or resolve pending work before moving the home")
        proofs = dict(password=password, answer=answer) if password and answer else (
            dict(password=password, recovery=recovery) if password and recovery else
            dict(answer=answer, recovery=recovery) if answer and recovery else {})
        if len(proofs) != 2:
            raise JournalError("Enter any two owner credentials")
        owner = self.runtime.trust._owner_credential(proofs)
        config = self.store.config
        endpoints = self._home_endpoints()
        if not endpoints:
            raise JournalError("Reconnect to the paired home on the local network before moving")
        home_key = config["home_key"]
        client = PinnedLocalClient(endpoints[0], self._home_certificate(), timeout=10)
        client_state_path = self.directory / "client.state"
        if client_state_path.is_symlink():
            raise JournalError("The local move recovery record is unsafe; preserve it for repair")
        client_state = read_slot(client_state_path) if client_state_path.exists() else None
        if client_state and (client_state.get("profile"), client_state.get("previous"), client_state.get("target")) != (
                config["profile"], config["generation"], config["device"]):
            raise JournalError("A different move is resumable; preserve its recovery record")
        if client_state:
            intent = client_state["intent"]
        else:
            intent_body = dict(type="journal-move-intent", profile=config["profile"], generation=config["generation"],
                               target=config["device"], target_key=self.identity.public_key, nonce=os.urandom(32).hex())
            intent = seal(intent_body, owner.sign).decode()
            client_state = dict(profile=config["profile"], previous=config["generation"], target=config["device"],
                                intent=intent, transition="")
            write_slot(client_state_path, client_state)
        cutoff_result = await self._call(client, home_key, "authorize", dict(intent=intent))
        cutoff = cutoff_result["cutoff"]
        if client_state["transition"]:
            transition_wire = client_state["transition"].encode()
            transition_body = unpack(transition_wire)["body"]
            if transition_body["cutoff"] != cutoff:
                raise JournalError("The resumed home freeze differs from the saved move")
        else:
            transition = dict(profile=config["profile"], previous=config["generation"], generation=str(uuid4()),
                              home=config["device"], home_key=config["origin_key"], owner_key=owner.public_key,
                              version=self.memory.state()["version"] + 1, mode="move", nonce=os.urandom(32).hex(), cutoff=cutoff)
            transition_wire = seal(transition, owner.sign)
            client_state["transition"] = transition_wire.decode()
            write_slot(client_state_path, client_state, replace=True)
        metadata = await self._call(client, home_key, "metadata", {})
        if metadata["cutoff"] != cutoff:
            raise JournalError("The home checkpoint changed after freeze")
        self._check_transfer_metadata(metadata)
        source = await self._download(metadata, client, home_key)
        from lightning.sync.journal.snapshots import repair
        repair(self.store, source, metadata["manifest"].encode(), source_key=self.store.db.copy_key())
        source.unlink(missing_ok=True)
        transfer_path = await self._download_transfer(metadata, client, home_key)
        self._install_transfer(transfer_path, metadata)
        transfer_path.unlink(missing_ok=True)
        prepared = self.memory.prepare(self.store, transition_wire, self.identity.sign)
        retired = await self._call(client, home_key, "retire", dict(transition=transition_wire.decode(), prepared=prepared.decode()))
        self.memory.activate_move(self.store, transition_wire, prepared, retired["retired"].encode(),
                                  old_home_key=home_key, home_signer=self.identity.sign)
        from lightning.sync.journal.home import JournalHome
        from lightning.sync.journal.membership import Membership
        self.device.home = JournalHome(self.store, self.identity.sign)
        for identifier, member in Membership(self.device).state()["members"].items():
            self.device.home.approve_origin(identifier, member["incarnation"], member["key"])
        self.device.flush_home()
        client_state_path.unlink(missing_ok=True)
        return "The home moved after the paired device verified and the old home retired the final checkpoint."

    async def _call(self, client, home_key, operation, value):
        config = self.store.config
        nonce = os.urandom(32).hex()
        wire = seal(dict(type="journal-move", profile=config["profile"], generation=config["generation"],
                         sender=config["device"], incarnation=config["incarnation"], operation=operation,
                         nonce=nonce, value=value), self.identity.sign)
        response = unpack(await client(wire))
        authenticate(response, home_key)
        body = response["body"]
        if set(body) != {"type", "nonce", "result"} or body["type"] != "journal-move-reply" or body["nonce"] != nonce:
            raise JournalError("Authority reply belongs to another move request")
        return body["result"]

    async def _download(self, metadata, client, home_key):
        descriptor, name = tempfile.mkstemp(prefix=".journal-move-", suffix=".db", dir=self.directory)
        path = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                result_hash = hashlib.sha256()
                total = 0
                for index in range(metadata["chunks"]):
                    result = await self._call(client, home_key, "chunk", dict(index=index))
                    if result["index"] != index:
                        raise JournalError("Checkpoint chunk order changed")
                    data = decode(result["data"])
                    if len(data) > CHUNK_SIZE or hashlib.sha256(data).hexdigest() != result["sha256"]:
                        raise JournalError("Checkpoint chunk failed its transport hash")
                    total += len(data)
                    if total > MAX_CHECKPOINT:
                        raise JournalError("Checkpoint exceeds the handoff limit")
                    handle.write(data); result_hash.update(data)
                handle.flush(); os.fsync(handle.fileno())
            manifest = unpack(metadata["manifest"].encode())["body"]
            if total != manifest["size"] or result_hash.hexdigest() != manifest["sha256"]:
                raise JournalError("Checkpoint differs from its signed manifest")
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def _download_transfer(self, metadata, client, home_key):
        descriptor, name = tempfile.mkstemp(prefix=".journal-move-", suffix=".rows", dir=self.directory)
        path = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                hasher, total = hashlib.sha256(), 0
                for index in range(metadata["transfer_chunks"]):
                    result = await self._call(client, home_key, "transfer", dict(index=index))
                    if result["index"] != index:
                        raise JournalError("Home-state chunk order changed")
                    data = decode(result["data"])
                    if (len(data) > TRANSFER_CHUNK or hashlib.sha256(data).hexdigest() != result["sha256"]):
                        raise JournalError("Home-state chunk failed its transport hash")
                    total += len(data)
                    if total > MAX_CHECKPOINT:
                        raise JournalError("Home-state transfer exceeds the handoff limit")
                    handle.write(data); hasher.update(data)
                handle.flush(); os.fsync(handle.fileno())
            if total != metadata["transfer_size"] or hasher.hexdigest() != metadata["transfer_hash"]:
                raise JournalError("Home-state transfer differs from its frozen manifest")
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _check_transfer_metadata(metadata):
        fields(metadata, ("manifest", "cutoff", "chunks", "transfer_chunks", "transfer_size", "transfer_hash", "transfer_items"))
        for key in ("chunks", "transfer_chunks", "transfer_size", "transfer_items"):
            number(metadata[key])
        if (type(metadata["manifest"]) is not str or metadata["chunks"] < 1
                or metadata["transfer_size"] > MAX_CHECKPOINT
                or metadata["transfer_chunks"] != (metadata["transfer_size"] + TRANSFER_CHUNK - 1) // TRANSFER_CHUNK
                or metadata["chunks"] > (MAX_CHECKPOINT + CHUNK_SIZE - 1) // CHUNK_SIZE
                or metadata["transfer_items"] > MAX_CHECKPOINT):
            raise JournalError("The frozen move manifest exceeds local transfer limits")
        hash_value(metadata["transfer_hash"])

    def _install_transfer(self, path, metadata):
        import base64
        if path.is_symlink() or path.stat().st_size != metadata["transfer_size"]:
            raise JournalError("Invalid home-state transfer file")
        count = 0
        with self.store.db.transaction():
            for table in TABLES:
                self.store.db.execute(f"DELETE FROM {table}")
            with path.open("rb") as handle:
                previous_table = -1
                for line in handle:
                    count += 1
                    try:
                        item = json.loads(line)
                    except (ValueError, TypeError) as error:
                        raise JournalError("Invalid transferred home-state row") from error
                    if _line(item) + b"\n" != line or type(item) is not dict or set(item) != {"table", "values"} or item["table"] not in TABLES:
                        raise JournalError("Invalid transferred home authority row")
                    table_index = TABLES.index(item["table"])
                    if table_index < previous_table:
                        raise JournalError("Transferred home-state order changed")
                    previous_table = table_index
                    columns = [row["name"] for row in self.store.db.all(f"PRAGMA table_info({item['table']})")]
                    values = item["values"]
                    if type(values) is not list or len(values) != len(columns):
                        raise JournalError("Transferred home row schema changed")
                    normalized = []
                    for cell in values:
                        if type(cell) is not dict or len(cell) != 1:
                            raise JournalError("Invalid transferred home value")
                        normalized.append(base64.b64decode(cell["bytes"], validate=True) if "bytes" in cell else cell["value"])
                    self.store.db.execute(f"INSERT INTO {item['table']}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", normalized)
        if count != metadata["transfer_items"]:
            raise JournalError("Home-state row count differs from its frozen manifest")

    def _home_endpoints(self):
        value = self.store.db.scalar("SELECT value FROM journal_local WHERE name='local_endpoints'")
        endpoints = json.loads(value) if value else []
        return [item.replace("/exchange", "/authority/exchange") for item in endpoints if type(item) is str and item.endswith("/exchange")]

    def _home_certificate(self):
        value = self.store.db.scalar("SELECT value FROM journal_local WHERE name='home_certificate'")
        if not value:
            from lightning.runtime.session import read_slot
            enrollment = self.runtime.paths.data_dir / "enrollment.json"
            if enrollment.exists():
                value = read_slot(enrollment).get("candidate", {}).get("certificate")
        if not value:
            raise JournalError("The paired home certificate is unavailable; reconnect pairing")
        return value if isinstance(value, str) and value.startswith("-----BEGIN CERTIFICATE-----") else json.loads(value)
