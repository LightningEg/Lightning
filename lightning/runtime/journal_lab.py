"""Password-protected, persistent dummy home/PC laboratory on loopback only.

Run: python -m lightning.runtime.journal_lab --dummy --root /path/to/journal-lab
This is an engineering preview, not the production profile launcher or pairing.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import hmac
import json
import os
import secrets
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

import uvicorn
from starlette.responses import PlainTextResponse, RedirectResponse

from lightning.bootstrap import build
from lightning.core.dates import today
from lightning.runtime.instance import InstanceLock
from lightning.runtime.session import read_slot, write_slot
from lightning.security.keys import create_key_file, new_recovery_key, unwrap_key
from lightning.sync.identity import load_or_create
from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import attach, initialize
from lightning.sync.journal.home import JournalHome
from lightning.sync.journal.local import LocalChannel
from lightning.ui.journal import create_journal_app


def open_lab(root, password):
    """Caller holds the root lock; every DB stays on this owning thread."""
    root = Path(root)
    marker = root / "journal-lab.json"
    fresh = not marker.exists()
    if fresh:
        if any(path.name != "instance.lock" for path in root.iterdir()):
            raise JournalError("Use an empty directory for a new dummy journal lab")
        key = os.urandom(32)
        # The test runner does not implement recovery. The normal key wrapper is
        # retained; a forgotten lab password requires a new empty dummy lab.
        write_slot(root / "keys.json", create_key_file(key, password, new_recovery_key(), "Dummy lab answer", "dummy"))
        config = dict(format=1, dummy=True, profile=str(uuid4()), generation=str(uuid4()))
    else:
        config = read_slot(marker)
        if config.get("format") != 1 or config.get("dummy") is not True:
            raise JournalError("This directory is not a supported dummy journal lab")
        key = unwrap_key(read_slot(root / "keys.json"), password)
    if not fresh:
        for name in ("Home", "PC"):
            for filename in ("device.json", "device-key.pem", "device-cert.pem"):
                path = root / f"identity-{name}" / filename
                if path.is_symlink() or not path.is_file():
                    raise JournalError("The dummy device identity is missing. Preserve this directory for repair")
    identities = [load_or_create(root / f"identity-{name}", name) for name in ("Home", "PC")]
    stores = []
    try:
        for index, identity in enumerate(identities):
            path = root / f"device-{index}.db"
            if fresh and index:
                # The PC starts from the home's verified checkpoint, as a real replica does.
                from lightning.sync.journal.snapshots import checkpoint_replica
                checkpoint_replica(stores[0], path, identities[0].sign, device=identity.device_id,
                                   incarnation=str(uuid4()), origin_key=identity.public_key)
            c = build(path, key=key, experimental_journal=not fresh or bool(index))
            try:
                if fresh and not index:
                    c.account_flows.open_account("Bank", "BANK", today().isoformat(), "1000")
                    c.account_flows.open_account("Wallet", "CASH", today().isoformat(), "100")
                    store = initialize(c, profile=config["profile"], generation=config["generation"],
                        device=identity.device_id, incarnation=str(uuid4()), home_key=identities[0].public_key,
                        origin_key=identity.public_key, role="home", dummy_profile=True)
                else:
                    store = attach(c)
                    if (store.config["device"] != identity.device_id or store.config["origin_key"] != identity.public_key
                            or store.config["profile"] != config["profile"] or store.config["generation"] != config["generation"]):
                        raise JournalError("The dummy device identity changed; preserve the directory for repair")
                stores.append(store)
            except BaseException:
                c.db.close()
                raise
        home = JournalHome(stores[0], identities[0].sign)
        if fresh:
            secret = os.urandom(32).hex()
            for store, identity in zip(stores, identities):
                home.approve_origin(identity.device_id, store.config["incarnation"], identity.public_key)
                with store.db.transaction():
                    store.db.execute("INSERT INTO journal_local VALUES('transport',?)", (secret,))
            write_slot(marker, config)
        transport_key = bytes.fromhex(stores[0].db.scalar("SELECT value FROM journal_local WHERE name='transport'"))
        devices = [JournalDevice(stores[0], identities[0], home), JournalDevice(stores[1], identities[1])]
        for device, name in zip(devices, ("Home", "PC")):
            if device.store.db.scalar("SELECT value FROM journal_local WHERE name='authority_enrolled'"):
                from lightning.sync.journal.authority import AuthorityMemory
                authority = AuthorityMemory(root / f"authority-{name}.db", profile=config["profile"])
                authority.bind(device.store)
        devices[0].flush_home()
        return devices, transport_key
    except BaseException:
        for store in stores:
            if store.authority:
                store.authority.close()
            store.close()
        raise


class LaunchGate:
    """A 30-second single-use local launch code becomes an HttpOnly cookie."""
    def __init__(self, app, session_token):
        self.app, self.token = app, session_token
        self.code, self.expiry, self.used = secrets.token_urlsafe(24), time.monotonic() + 30, False

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/open":
            values = parse_qs(scope.get("query_string", b"").decode("ascii", errors="replace"))
            code = values.get("code", [""])[0]
            if self.used or time.monotonic() > self.expiry or not hmac.compare_digest(code.encode("utf-8"), self.code.encode("utf-8")):
                return await PlainTextResponse("Open the lab again from its launcher.", status_code=401)(scope, receive, send)
            self.used = True
            response = RedirectResponse("/", status_code=303)
            response.set_cookie("journal_session", self.token, httponly=True, samesite="strict")
            response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "same-origin"})
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)


class AppGate:
    """The app's own screens in a lab window: only the launched session may use
    them, and a saved change starts a sync at once instead of waiting a round."""
    def __init__(self, app, session_token, after_write=None):
        self.app, self.token, self.after_write = app, session_token, after_write

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not scope["path"].startswith("/static/"):
            cookies = dict(item.strip().split("=", 1) for item in _header(scope, b"cookie").split(";") if "=" in item)
            if not hmac.compare_digest(cookies.get("journal_session", "").encode("utf-8"), self.token.encode("utf-8")):
                return await PlainTextResponse("Unlock this experimental profile first.", status_code=401)(scope, receive, send)
        await self.app(scope, receive, send)
        if scope["type"] == "http" and scope["method"] == "POST" and self.after_write is not None:
            self.after_write()


def _header(scope, name):
    return next((value.decode("latin-1") for key, value in scope.get("headers", []) if key == name), "")


class LabServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # asyncio.run owns Ctrl-C and cancels all three servers together.
        yield


async def serve(devices, transport_key, port, *, browser=True, mailbox_origin=None, internet_only=False, full_app=False):
    home, pc = devices
    home_channel = LocalChannel(home, transport_key=transport_key, peers={pc.identity.device_id: pc.identity.public_key})
    pc_channel = LocalChannel(pc, transport_key=transport_key, peers={home.identity.device_id: home.identity.public_key})
    from lightning.sync.journal.membership import Membership
    members = {device.identity.device_id:dict(key=device.identity.public_key,incarnation=device.store.config["incarnation"]) for device in devices}
    for device, channel in ((home, home_channel), (pc, pc_channel)):
        membership = Membership(device)
        if not device.store.db.scalar("SELECT value FROM journal_local WHERE name='membership'"):
            membership.initialize(members,transport_key)
        membership.bind(channel)
        with device.store.db.transaction():
            device.store.db.execute("INSERT OR REPLACE INTO journal_local VALUES('paired_names',?)",
                (json.dumps({item.identity.device_id:item.identity.name for item in devices}),))
    internet = []
    if mailbox_origin:
        from lightning.runtime.journal_internet import JournalInternet
        internet = [JournalInternet(device, mailbox_origin) for device in devices]
    if internet_only and not internet:
        raise JournalError("Configure the mailbox before choosing internet-only transport")
    from lightning.runtime.journal_routes import LocalFirstSync
    router = LocalFirstSync(pc, pc_channel, home_id=home.identity.device_id,
        certificate=home.identity.cert_path.read_text(), endpoints=[f"https://127.0.0.1:{port + 2}/exchange"],
        internet=internet[1] if internet else None)
    from lightning.runtime.journal_pairing import NearbyPairing
    pairings = [NearbyPairing(home,key_document=lambda:read_slot(Path(home.store.db.path).parent/'keys.json'),
        owner_document=(lambda:read_slot(Path(home.store.db.path).parent/'owner-authority.json')) if home.store.authority else None), NearbyPairing(pc)]
    async def sync():
        if not internet_only:
            return await router.synchronize()
        await internet[0].catch_up(foreground=True)
        await internet[1].catch_up(foreground=True)
    token = secrets.token_urlsafe(32)
    if full_app:
        # The app's own screens; covered writes travel as journal commands (`proxy.JournalServices`).
        from lightning.sync.journal.proxy import JournalServices
        from lightning.ui.web import create_app
        pending = set()
        def after_write():
            task = asyncio.get_running_loop().create_task(sync())
            pending.add(task)
            task.add_done_callback(lambda done: (pending.discard(done), done.cancelled() or done.exception()))
        apps = [LaunchGate(AppGate(create_app(JournalServices(home)), token), token),
                LaunchGate(AppGate(create_app(JournalServices(pc)), token, after_write), token)]
    else:
        apps = [LaunchGate(create_journal_app(home, session_token=token, channel=home_channel, pairing=pairings[0]), token),
                LaunchGate(create_journal_app(pc, session_token=token, synchronize=sync, pairing=pairings[1]), token)]
    protocol = create_journal_app(home, session_token=token, channel=home_channel, pairing=pairings[0])
    servers = [LabServer(uvicorn.Config(app, host="127.0.0.1", port=port + index, access_log=False, log_level="error", timeout_graceful_shutdown=5))
               for index, app in enumerate(apps)]
    servers.append(LabServer(home.identity.configure_uvicorn_tls(uvicorn.Config(
        protocol, host="0.0.0.0", port=port + 2,
        access_log=False, log_level="error", timeout_graceful_shutdown=5))))
    async def launch():
        for _ in range(100):
            if all(server.started for server in servers):
                if browser:
                    for index, app in enumerate(apps):
                        webbrowser.open(f"http://127.0.0.1:{port + index}/open?code={app.code}")
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("The dummy lab could not start its local servers")
    async def reconnect():
        while True:
            await asyncio.sleep(30)
            try:
                if internet and not internet_only:
                    await asyncio.gather(sync(), internet[0].catch_up())
                else:
                    await sync()
            except (OSError, TimeoutError, JournalError):
                pass
    from lightning.sync.journal.discovery import LanResponder, DISCOVERY_PORT
    discovery_transport = None
    try:
        discovery_transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda:LanResponder(home_channel,tls_port=port+2,nearby=pairings[0].advertise),local_addr=("0.0.0.0",DISCOVERY_PORT))
    except OSError:
        pass  # Pinned cached addresses and the optional cloud route still work.
    running = asyncio.gather(*(server.serve() for server in servers), launch())
    periodic = asyncio.create_task(reconnect())
    try:
        await asyncio.shield(running)
    finally:
        if discovery_transport:
            discovery_transport.close()
        for server in servers:
            server.should_exit = True
        periodic.cancel()
        await asyncio.gather(periodic, return_exceptions=True)
        # Let ASGI lifespans drain/cancel sync before profile keys/connections close.
        await running
        for runtime in internet:
            await runtime.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dummy", action="store_true", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=47540)
    parser.add_argument("--mailbox-origin")
    parser.add_argument("--internet-only", action="store_true")
    parser.add_argument("--app", action="store_true", help="Open the app's own screens instead of the journal preview")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65533:
        parser.error("Choose a port between 1024 and 65533")
    password = getpass.getpass("Dummy lab password (needed again after restart): ")
    if not password:
        parser.error("Enter a password for the encrypted dummy profiles")
    args.root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with InstanceLock(args.root / "instance.lock"):
        devices, key = open_lab(args.root, password)
        try:
            print("Opening the persistent dummy home and PC. Press Ctrl-C to close both.")
            asyncio.run(serve(devices, key, args.port, mailbox_origin=args.mailbox_origin, internet_only=args.internet_only,
                              full_app=args.app))
        except KeyboardInterrupt:
            pass
        finally:
            for device in devices:
                if device.store.authority:
                    device.store.authority.close()
                device.store.close()


if __name__ == "__main__":
    main()
