"""The journal runtime for an explicitly selected encrypted app profile.

The session owns the database and its lock. Network requests and Android wake
requests return to that session's event loop and request gate before touching it.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import socket
from contextlib import suppress
from pathlib import Path

from lightning.sync.identity import load_or_create
from lightning.sync.journal.authority import AuthorityMemory
from lightning.sync.journal.codec import JournalError, seal
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import attach
from lightning.sync.journal.home import JournalHome
from lightning.sync.journal.local import LocalChannel
from lightning.sync.journal.membership import Membership
from lightning.sync.journal.owner import OwnerCredential
from lightning.sync.journal.proxy import JournalServices


class CloudPlaceholder:
    """An unconfigured carrier never acknowledges or discards saved work."""
    configured = False

    async def catch_up(self, **kwargs):
        return False

    async def publish(self, wire):
        raise JournalError("Cloud recovery is not configured. Your local edits are preserved.")


def authority_path(paths, profile, device):
    folder = paths.data_dir.parent / ".journal-authority"
    if folder.is_symlink():
        raise JournalError("The independent authority folder must not be a symbolic link")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder / f"{profile}.{device}.db"


def provision(store, identity, paths, *, password, recovery, answer):
    """Resume owner enrollment without replacing an already committed credential."""
    from .session import AttemptGuard, read_slot, write_slot
    from lightning.sync.journal.membership import Membership
    owner_path = paths.data_dir / "owner-authority.json"
    if owner_path.exists():
        wrapper = read_slot(owner_path)
        owner = OwnerCredential.unlock(wrapper, dict(password=password, answer=answer),
                                       guard=AttemptGuard(paths.data_dir / "owner-attempts.json"))
    else:
        owner, wrapper = OwnerCredential.create(store.config["profile"], password=password,
                                                recovery=recovery, answer=answer)
        write_slot(owner_path, wrapper)
    config = store.config
    control = authority_path(paths, config["profile"], identity.device_id)
    if not control.exists():
        wire = seal(dict(type="authority-enrollment", version=1, profile=config["profile"],
                         generation=config["generation"], home=identity.device_id,
                         home_key=identity.public_key, owner_key=owner.public_key), owner.sign)
        memory = AuthorityMemory.enroll(control, wire)
    else:
        memory = AuthorityMemory(control, profile=config["profile"])
    try:
        if memory.state()["owner_key"] != owner.public_key:
            raise JournalError("The owner credential does not match the saved authority")
        memory.bind(store)
        device = JournalDevice(store, identity, JournalHome(store, identity.sign))
        device.home.approve_origin(identity.device_id, config["incarnation"], identity.public_key)
        membership = Membership(device)
        if not store.db.scalar("SELECT value FROM journal_local WHERE name='membership'"):
            membership.initialize({identity.device_id: dict(key=identity.public_key,
                incarnation=config["incarnation"])}, os.urandom(32))
        write_slot(paths.data_dir / "journal-native.json", dict(format=1, profile=config["profile"],
                   device=identity.device_id), replace=(paths.data_dir / "journal-native.json").exists())
    finally:
        memory.close()
        store.authority = None


class JournalRuntime:
    def __init__(self, container, paths, key_document):
        from .session import read_slot
        self.container, self.paths, self.key_document = container, paths, key_document
        self.closed, self.task, self.server, self.transport = False, None, None, None
        self.gate, self.loop = None, None
        self._sync_busy = False
        self.cloud = CloudPlaceholder()
        identity_root = paths.data_dir / "identity"
        for name in ("device.json", "device-key.pem", "device-cert.pem"):
            path = identity_root / name
            if path.is_symlink() or not path.is_file():
                raise JournalError("This device's journal identity is missing. Reconnect from the current home.")
        self.identity = load_or_create(identity_root, "This device")
        self.store = attach(container)
        config = self.store.config
        if config["device"] != self.identity.device_id or config["origin_key"] != self.identity.public_key:
            raise JournalError("This profile belongs to another device. Pair this device with its home.")
        self.owner_document = read_slot(paths.data_dir / "owner-authority.json")
        self.memory = AuthorityMemory(authority_path(paths, config["profile"], config["device"]),
                                      profile=config["profile"])
        try:
            self.memory.bind(self.store)
            from lightning.sync.journal.upgrades import complete_upgrade
            complete_upgrade(self.store, self.identity.sign, paths.backups_dir)
            self.device = JournalDevice(self.store, self.identity,
                JournalHome(self.store, self.identity.sign) if config["role"] == "home" else None)
            membership = Membership(self.device)
            state = membership.state()
            secret = bytes.fromhex(self.store.db.scalar("SELECT value FROM journal_local WHERE name='transport'"))
            self.channel = LocalChannel(self.device, transport_key=secret,
                peers={identifier: member["key"] for identifier, member in state["members"].items()},
                epoch=state["epoch"])
            membership.bind(self.channel)
            from .journal_pairing import NearbyPairing
            from .session import read_keys
            self.pairing = NearbyPairing(self.device, key_document=lambda: read_keys(paths),
                owner_document=lambda: read_slot(paths.data_dir / "owner-authority.json"))
            from .journal_trust import JournalTrustRuntime
            self.trust = JournalTrustRuntime(self.device, self.pairing, paths,
                self.owner_document, owner_path=paths.data_dir / "owner-authority.json", internet=self.cloud)
            from .journal_move import JournalMoveRuntime
            self.move = JournalMoveRuntime(self)
            self.trust.move_runtime = self.move
            self.services = JournalServices(self.device, backup=self.backup)
            self.automation = None
            if self.device.home:
                from lightning.sync.journal.history import attach_home_history
                attach_home_history(container, self.store.adapter)
                from lightning.sync.journal.automation import JournalAutomation
                self.automation = JournalAutomation(self.device)
        except BaseException:
            self.memory.close()
            raise

    def start(self, gate, *, files_dir=None):
        if self.task is not None or self.closed:
            return
        self.gate, self.loop = gate, asyncio.get_running_loop()
        self.files_dir = Path(files_dir) if files_dir else None
        if self.files_dir is not None:
            from .journal_android import register
            register(self.files_dir, self, self.loop, self.synchronize)
        self.task = self.loop.create_task(self._run())

    async def synchronize(self):
        if self.closed:
            return "locked"
        if self.gate is None:
            return "offline"
        async with self.gate.mutex:
            return await self._synchronize()

    async def _synchronize(self):
        if self._sync_busy:
            return "syncing"
        self._sync_busy = True
        try:
            return await self._sync_round()
        finally:
            self._sync_busy = False

    async def _sync_round(self):
        if self.closed:
            return "locked"
        self.refresh_authority()
        before = self.store.cursor()
        if self.device.home:
            self.device.flush_home()
            if self.automation:
                self.automation.tick()
            return "synced" if self.store.cursor() != before else "idle"
        from .journal_routes import LocalFirstSync
        certificate = self.store.db.scalar("SELECT value FROM journal_local WHERE name='home_certificate'")
        if not certificate:
            from .session import read_slot
            enrollment = self.paths.data_dir / "enrollment.json"
            if enrollment.exists():
                candidate = read_slot(enrollment).get("candidate", {})
                certificate = candidate.get("certificate")
        if not certificate:
            return "offline"
        router = LocalFirstSync(self.device, self.channel, home_id=self.memory.state()["home"],
                                certificate=certificate, internet=self.cloud, client_factory=self._client)
        try:
            reached = await router.synchronize()
        except (OSError, TimeoutError):
            return "offline"
        return "synced" if self.store.cursor() != before else "idle" if reached else "offline"

    def _client(self, endpoint, certificate, **options):
        """Release only the UI gate during network I/O; DB work stays on its loop."""
        from lightning.sync.journal.local import PinnedLocalClient
        client = PinnedLocalClient(endpoint, certificate, **options)

        async def send(wire):
            generation = self.store.config["generation"]
            self.gate.mutex.release()
            try:
                result = await client(wire)
            finally:
                await self.gate.mutex.acquire()
            if self.closed:
                raise JournalError("The profile was locked while synchronization was waiting")
            if generation != self.store.config["generation"]:
                raise JournalError("Authority changed while synchronization was waiting; retry on the current home")
            return result

        return send

    def refresh_authority(self):
        """Retirement immediately removes home automation and confirmation paths."""
        active_home = self.memory.can_confirm(self.store)
        if active_home and self.device.home is None:
            self.device.home = JournalHome(self.store, self.identity.sign)
        elif not active_home and self.device.home is not None:
            self.device.home = None
            self.store.adapter.detach_history()
        if active_home and self.automation is None:
            from lightning.sync.journal.history import attach_home_history
            attach_home_history(self.container, self.store.adapter)
            from lightning.sync.journal.automation import JournalAutomation
            self.automation = JournalAutomation(self.device)
        elif not active_home and self.automation is not None:
            self.automation.close()
            self.automation = None
        # Pairing handlers are captured by the listener; preserve their object
        # identity while rebuilding home-only desk/enrollment capabilities.
        if (self.pairing.desk is not None) != active_home:
            from .journal_pairing import NearbyPairing
            from .session import read_keys, read_slot
            replacement = NearbyPairing(self.device, key_document=lambda: read_keys(self.paths),
                owner_document=lambda: read_slot(self.paths.data_dir / "owner-authority.json"))
            self.pairing.__dict__.update(replacement.__dict__)
        Membership(self.device).refresh(self.channel)

    def backup(self):
        from datetime import datetime, timezone
        from uuid import uuid4
        from lightning.sync.journal.backups import create
        from .session import read_keys, read_slot, write_slot
        self.paths.backups_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"{Path(self.store.db.path).stem}_backup_{datetime.now(timezone.utc):%Y-%m-%d}_"
        sequence = 1 + len(list(self.paths.backups_dir.glob(prefix + "*.db")))
        target = self.paths.backups_dir / f"{prefix}{sequence:03d}_{uuid4().hex[:8]}.db"
        wire = create(self.device, target, key_document=read_keys(self.paths),
                      owner_document=read_slot(self.paths.data_dir / "owner-authority.json"))
        write_slot(target.with_suffix(".journal-manifest.json"), json.loads(wire))
        return target

    async def _run(self):
        from lightning.sync.journal.discovery import DISCOVERY_PORT, LanResponder
        from lightning.ui.journal import create_journal_app
        from .journal_lab import LabServer
        import uvicorn
        server_task = None
        try:
            with socket.socket() as probe:
                probe.bind(("0.0.0.0", 0))
                port = probe.getsockname()[1]
            protocol = create_journal_app(self.device, session_token=secrets.token_urlsafe(32),
                                          channel=self.channel, pairing=self.pairing, move=self.move)
            guarded = _ProtocolGate(protocol, self)
            self.server = LabServer(self.identity.configure_uvicorn_tls(uvicorn.Config(
                guarded, host="0.0.0.0", port=port,
                access_log=False, log_level="error", timeout_graceful_shutdown=1,
                limit_concurrency=32, backlog=32, timeout_keep_alive=3)))
            server_task = asyncio.create_task(self.server.serve())
            try:
                self.transport, _ = await self.loop.create_datagram_endpoint(
                    lambda: LanResponder(self.channel, tls_port=port, nearby=self.pairing.advertise),
                    local_addr=("0.0.0.0", DISCOVERY_PORT))
            except OSError:
                pass
            while not self.closed:
                try:
                    await self.synchronize()
                except (JournalError, OSError, TimeoutError):
                    pass  # Saved edits remain queued; the next bounded round can retry.
                await asyncio.sleep(30)
        finally:
            if self.transport:
                self.transport.close()
            if self.server:
                self.server.should_exit = True
            if server_task:
                server_task.cancel()
                with suppress(asyncio.CancelledError):
                    await server_task

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.automation:
            self.automation.close()
        if getattr(self, "files_dir", None) is not None:
            from .journal_android import unregister
            unregister(self.files_dir, self)
        if self.transport:
            self.transport.close()
        if self.task:
            self.task.cancel()
        if self.server:
            self.server.should_exit = True
        self.memory.close()


class _ProtocolGate:
    def __init__(self, app, runtime):
        from lightning.sync.journal.request_limits import PairingRequestLimits
        self.app, self.runtime = app, runtime
        self.pairing_limits = PairingRequestLimits()

    async def __call__(self, scope, receive, send):
        from starlette.responses import PlainTextResponse
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] not in {"/exchange", "/pairing/exchange", "/membership/exchange", "/enrollment/exchange", "/authority/exchange"}:
            return await PlainTextResponse("Journal protocol only", 404)(scope, receive, send)
        pairing = scope["path"] == "/pairing/exchange"
        if pairing:
            peer = str((scope.get("client") or ("unknown",0))[0])
            if not self.pairing_limits.enter(peer):
                return await PlainTextResponse("Pairing request budget exceeded", 429)(scope, receive, send)
            original_receive = receive
            try:
                headers = dict(scope.get("headers", []))
                length = headers.get(b"content-length", b"0")
                if not length.isdigit():
                    return await PlainTextResponse("Invalid body length", 400)(scope, receive, send)
                if int(length) > 4096:
                    return await PlainTextResponse("Pairing request limit exceeded", 413)(scope, receive, send)
                async def bounded_body():
                    body = bytearray()
                    while True:
                        message = await original_receive()
                        if message["type"] == "http.disconnect":
                            raise ConnectionError("Peer disconnected")
                        body.extend(message.get("body", b""))
                        if len(body) > 4096:
                            raise ValueError("Pairing body too large")
                        if not message.get("more_body", False):
                            return bytes(body)
                try:
                    body = await asyncio.wait_for(bounded_body(), timeout=3)
                except (TimeoutError, ConnectionError):
                    return await PlainTextResponse("Pairing request timed out", 408)(scope, original_receive, send)
                except ValueError:
                    return await PlainTextResponse("Pairing request limit exceeded", 413)(scope, original_receive, send)
                delivered = False
                async def buffered_receive():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return dict(type="http.request", body=body, more_body=False)
                    return await original_receive()
                receive = buffered_receive
                await self._locked(scope, receive, send)
            finally:
                self.pairing_limits.leave()
            return
        return await self._locked(scope, receive, send)

    async def _locked(self, scope, receive, send):
        from starlette.responses import PlainTextResponse
        async with self.runtime.gate.mutex:
            if self.runtime.closed:
                return await PlainTextResponse("Profile locked", 423)(scope, receive, send)
            return await self.app(scope, receive, send)
