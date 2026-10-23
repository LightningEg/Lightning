"""Multiple devices inside the running app: the phone that holds a ledger and the PC that borrows it.

Everything here lives in this device's own app data (`root`), never in a profile folder:

    <root>/device/                 this device's identity (lightning.sync.identity)
    <root>/home/<profile folder>/  a ledger this device holds and lends: control store, checkpoints, home.json
    <root>/borrowed/<profile id>/  a ledger this PC borrows: control store, working copy, its own key slot

The sync link runs on its own threads. Whatever it needs from the open profile goes through `AppBridge`, which
asks the request gate on the app's event loop, so a lend never starts in the middle of a request.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from lightning.sync.control import ControlStore
from lightning.sync.identity import DEFAULT_PORT, DeviceIdentity, load_or_create, local_address
from lightning.sync.service import BorrowerNode, HomeNode, LinkDown
from lightning.sync.state import BorrowerState, HomeState, ProtocolError

from .paths import ProfilePaths, app_data_root, resolve_profile

HOME_META = "home.json"
LENDING_MARK = "lending.json"   # beside the ledger: it has a lending record on this device (review H1)
MOVING_MARK = "moving.json"     # on the PC, while a profile is moving to the phone (review H3, M10)


def arriving_path(live: Path) -> Path:
    """On the phone, a moved ledger waits here, hidden from the profile list, until the PC that sent it confirms
    it kept its copy read only (review H3)."""
    return Path(live).with_suffix(".arriving")
STATUS_TIMEOUT = 5


def mark_lending(paths: ProfilePaths, profile_id: str) -> None:
    mark = Path(paths.data_dir) / LENDING_MARK
    if not mark.exists():
        mark.write_text(json.dumps({"profile_id": profile_id}), encoding="utf-8")


class AppBridge:
    """The home node's view of the app's open profile (lightning.sync.service.HomeBridge)."""

    def __init__(self, devices: "Devices", live: Path):
        self.devices, self.live = devices, Path(live)

    def _open_here(self) -> bool:
        session = self.devices.session
        return (session is not None and session.paths is not None and session.borrowed is None
                and Path(session.paths.db_path) == self.live)

    def key(self) -> bytes | None:
        return self.devices.session.sync_key if self._open_here() else None

    def set_mode(self, mode: str) -> None:
        if not self._open_here():
            return
        loop, gate = self.devices.loop, self.devices.gate
        if loop is None or gate is None:
            raise RuntimeError("The app is not running")
        asyncio.run_coroutine_threadsafe(gate.set_mode(mode), loop).result(120)


@dataclass(frozen=True)
class Borrowed:
    node: BorrowerNode
    profile_id: str
    name: str
    home_name: str

    @property
    def state(self) -> BorrowerState:
        return self.node.model.state


class Devices:
    def __init__(self, root: str | Path | None = None, *, port: int = DEFAULT_PORT, host: str = "0.0.0.0"):
        self.root = Path(root) if root is not None else app_data_root()
        self.port, self.host = port, host
        self.session = None      # the app's ProfileSession
        self.gate = None         # its SessionGate
        self.loop = None         # the app's event loop, set at startup
        self.server = None
        self.desk = None
        self._lock = threading.RLock()
        self._nodes: dict[Path, HomeNode] = {}
        self.last_arrival: Path | None = None  # the profile the last move into this phone stored

    # ------------------------------------------------------------ identity
    def identity(self, name: str | None = None) -> DeviceIdentity:
        folder = self.root / "device"
        if name is None:
            meta = folder / "device.json"
            name = json.loads(meta.read_text(encoding="utf-8"))["name"] if meta.exists() else "This device"
        return load_or_create(folder, name)

    def has_identity(self) -> bool:
        return (self.root / "device" / "device.json").exists()

    # ------------------------------------------------------------ the ledgers this device holds
    def home_folder(self, paths: ProfilePaths) -> Path | None:
        if paths.profile is None:
            return None  # only named profiles can be lent
        return self.root / "home" / paths.profile.profile_id

    def home_node(self, paths: ProfilePaths) -> HomeNode | None:
        folder = self.home_folder(paths)
        if folder is None or not (folder / "control.db").exists():
            return None
        return self._node(folder, Path(paths.db_path))

    def _node(self, folder: Path, live: Path) -> HomeNode:
        with self._lock:
            node = self._nodes.get(folder)
            if node is None:
                node = HomeNode(live_path=live, control_folder=folder, bridge=AppBridge(self, live))
                self._nodes[folder] = node
            return node

    def home_nodes(self) -> list[HomeNode]:
        nodes = []
        for meta in sorted((self.root / "home").glob(f"*/{HOME_META}")):
            try:
                live = Path(json.loads(meta.read_text(encoding="utf-8"))["live_path"])
                if (live.parent / "journal-native.json").exists():
                    continue
                if (live.exists() or arriving_path(live).exists()) and (meta.parent / "control.db").exists():
                    nodes.append(self._node(meta.parent, live))
            except (OSError, ValueError, KeyError):
                continue
        return nodes

    def enable_home(self, session, phone_name: str) -> HomeNode:
        if getattr(session, "journal", None) is not None:
            raise ProtocolError("BAD_REQUEST", "This profile uses edit synchronization. Open its Devices page.")
        """On the owning thread, profile unlocked and writable: make this device the ledger's home."""
        paths = session.paths
        folder = self.home_folder(paths)
        if folder is None or session.borrowed is not None:
            raise ProtocolError("BAD_REQUEST", "Only a profile kept on this device can be lent.")
        identity = self.identity(phone_name)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        HomeNode.enable(session.container.db, live_path=paths.db_path, control_folder=folder,
                        home_id=identity.device_id, bridge=AppBridge(self, paths.db_path))
        (folder / HOME_META).write_text(json.dumps({"live_path": str(paths.db_path)}), encoding="utf-8")
        mark_lending(paths, self.home_node(paths).profile_id)
        return self._node(folder, Path(paths.db_path))

    def lending_state(self, paths: ProfilePaths) -> str:
        """"none" (never lent), "ok", or "missing"/"damaged": the ledger was set up for lending but its record on
        this device is gone or unreadable (cleared app data, a copied profile). Then it must not open writable:
        a PC may hold it (review H1)."""
        if self.home_folder(paths) is None:
            return "none"
        marked = (Path(paths.data_dir) / LENDING_MARK).exists()
        try:
            node = self.home_node(paths)
            if node is None:
                return "missing" if marked else "none"
            node.model  # reads and checks the record
            return "ok"
        except Exception:  # noqa: BLE001 - ControlCorrupt, sqlite errors: never a fresh "at home"
            return "damaged"

    def role_for(self, selected: str) -> str:
        if (Path(selected).parent / "journal-native.json").exists() or (Path(selected).parent / "complete.json").exists():
            return "home"  # The journal runtime checks authority independently of v1 lending.
        """How a profile kept here may open: "home" (writable) or "reader" (lent away, a hand-back to finish,
        or a lending record missing or damaged). Decided before any connection opens."""
        try:
            paths = resolve_profile(db_path=selected)
        except (OSError, ValueError):
            return "home"
        state = self.lending_state(paths)
        if state == "none":
            return "home"
        if state != "ok":
            return "reader"
        try:
            return "home" if self.home_node(paths).writable() else "reader"
        except Exception:  # noqa: BLE001 - unreadable: read-only (review M9)
            return "reader"

    def keep_as_home(self, session, phone_name: str) -> HomeNode:
        if getattr(session, "journal", None) is not None:
            raise ProtocolError("BAD_REQUEST", "Use the synchronized profile's Devices page.")
        """The owner's repair when the lending record is missing or damaged: this copy becomes the ledger under a
        new lineage, so no PC copy from before can come back. PCs pair again. On the owning thread."""
        paths = session.paths
        folder = self.home_folder(paths)
        if folder is None:
            raise ProtocolError("BAD_REQUEST", "Only a profile kept on this device can be lent.")
        if folder.exists():
            folder.rename(folder.with_name(f"{folder.name}.damaged-{int(time.time())}"))
        with self._lock:
            self._nodes.pop(folder, None)
        identity = self.identity(phone_name)
        folder.mkdir(mode=0o700, parents=True)
        from lightning.sync.control import ControlStore, new_id
        from lightning.sync.copies import profile_id_of, schema_version
        from lightning.sync.service import compatibility
        from lightning.sync.state import HomeProtocolModel
        db = session.container.db
        profile_id = profile_id_of(db) or json.loads((Path(paths.data_dir) / LENDING_MARK).read_text())["profile_id"]
        ControlStore(folder).create(HomeProtocolModel(
            profile_id=profile_id, home_id=identity.device_id, lineage_id=new_id(), checkpoint_id=new_id(),
            checkpoint_sha256="0" * 64, compatibility=compatibility(db.copy_key(), schema_version(db)),
            paired_devices=set()))
        (folder / HOME_META).write_text(json.dumps({"live_path": str(paths.db_path)}), encoding="utf-8")
        mark_lending(paths, profile_id)
        return self._node(folder, Path(paths.db_path))

    def blocks_restore(self, selected: str) -> bool:
        """Restore must wait while the ledger is lent, mid hand-back, or its lending record is not readable."""
        from lightning.sync.control import blocks_restore
        try:
            paths = resolve_profile(db_path=selected)
        except (OSError, ValueError):
            return False
        state = self.lending_state(paths)
        if state == "none":
            return False
        if state != "ok":
            return True
        return blocks_restore(self.home_folder(paths))

    def after_unlock(self, paths: ProfilePaths) -> None:
        """Finish an interrupted hand-back and accept a copy that arrived while locked: on a worker thread,
        because it changes the session's mode through the gate."""
        try:
            node = self.home_node(paths) if self.lending_state(paths) == "ok" else None
        except Exception:  # noqa: BLE001 - a damaged record: the Devices page offers the repair (review M9)
            node = None
        if node is None:
            return

        def work():
            try:
                node.recover()
            except Exception:  # noqa: BLE001 - the state stays as recorded; the Devices page shows it
                pass
        threading.Thread(target=work, name="lightning-sync-recover", daemon=True).start()

    # ------------------------------------------------------------ listening for PCs (on the phone)
    def ensure_listener(self) -> None:
        from lightning.sync.transport import HomeServer, PairingDesk
        with self._lock:
            if self.server is not None:
                return
            self.desk = self.desk or PairingDesk()
            self.server = HomeServer(self.identity(), self.home_nodes, self.desk, host=self.host, port=self.port,
                                     on_authenticated=self._finish_arrival,
                                     arriving=lambda node: not node.live.exists()).start()

    def _finish_arrival(self, node: HomeNode) -> None:
        """The PC that moved this ledger here connected as its borrower: it kept its copy read only, so the
        ledger becomes a profile on this phone."""
        import os
        arriving = arriving_path(node.live)
        if arriving.exists() and not node.live.exists():
            os.replace(arriving, node.live)

    def arrived(self) -> bool:
        """The last move into this phone is confirmed by its PC (the receive page's "is here")."""
        return self.last_arrival is not None and self.last_arrival.exists()

    def start(self, loop, session, gate) -> None:
        self.loop, self.session, self.gate = loop, session, gate
        if getattr(session, "root", None) is not None:
            recover_moves(self, Path(session.root))
        if self.home_nodes():
            try:
                self.ensure_listener()
            except OSError:
                pass  # the port is busy: the Devices page says so when asked to pair

    def stop(self) -> None:
        with self._lock:
            if self.server is not None:
                self.server.stop()
                self.server = None

    def address(self) -> str:
        port = self.server.port if self.server is not None else self.port
        return f"{local_address()}:{port}"

    # ------------------------------------------------------------ the ledgers this PC borrows
    def borrowed(self) -> list[Borrowed]:
        found = []
        for meta in sorted((self.root / "borrowed").glob("*/profile.json")):
            try:
                from .paths import borrowed_profile
                paths = borrowed_profile(meta.parent.name, root=self.root)
                node = BorrowerNode(paths)
                model = node.model
                home = node.store.peer(model.home_id)
                found.append(Borrowed(node, model.profile_id, json.loads(meta.read_text(encoding="utf-8"))["name"],
                                      home.name if home else "your phone"))
            except (OSError, ValueError, KeyError, RuntimeError):
                continue
        return found

    def find_borrowed(self, profile_id: str) -> Borrowed | None:
        return next((b for b in self.borrowed() if b.profile_id == profile_id), None)

    def link(self, node: BorrowerNode, *, timeout: float | None = None):
        from lightning.sync.transport import link_to_home
        link = link_to_home(node, self.identity())
        if timeout is not None:
            link.timeout = timeout
        return link

    def hand_back_or_seal(self, node: BorrowerNode) -> str:
        """At close (Lock, Hand back, app exit): hand back when the phone answers, else keep the lend sealed
        here. Returns "accepted", "received" (the phone checks it at its next unlock), "sealed" or "returning"
        (sending started and will be retried)."""
        from lightning.sync.domain import Accepted, Status
        state = node.model.state
        if state not in (BorrowerState.BORROWING, BorrowerState.SEALED, BorrowerState.RETURNING):
            return state.value.lower()
        try:
            if state is not BorrowerState.RETURNING:
                self.link(node, timeout=STATUS_TIMEOUT).status(Status(node.model.device_id))
        except LinkDown:
            node.seal()
            return "sealed"
        except ProtocolError as refused:  # the phone answered but no longer knows this PC: say so
            node.seal()
            return "unpaired" if refused.code == "UNAUTHORIZED" else "sealed"
        try:
            receipt = node.hand_back(self.link(node)) if state is not BorrowerState.RETURNING \
                else node.check_return(self.link(node))
        except LinkDown:
            return "returning"
        except ProtocolError:  # taken back, or refused: the copy stays here, read only (review M7)
            return "refused"
        return "accepted" if isinstance(receipt, Accepted) else "received"

    def taken_back(self, node: BorrowerNode) -> bool:
        """Before reopening a sealed copy: whether the phone took the ledger back meanwhile (review L13). Out of
        reach counts as not: the PC keeps working offline, as sealing promises."""
        from lightning.sync.domain import Status
        model = node.model
        try:
            reply = self.link(node, timeout=STATUS_TIMEOUT).status(Status(model.device_id))
        except (LinkDown, OSError):
            return False
        except ProtocolError:
            return False
        if reply.lineage_id != model.lineage_id or reply.lent_to != model.device_id:
            node.store.borrower(lambda m: m.needs_repair())
            return True
        return False


def home_state_line(node: HomeNode | None, lending: str = "ok") -> str:
    """What the phone's banner says while its ledger is away, or "" at home."""
    text, values = home_state_message(node, lending)
    return text.format(**values) if values else text


def home_state_message(node: HomeNode | None, lending: str = "ok") -> tuple[str, dict]:
    """A system template plus literal peer data for the translated status banner."""
    if lending in ("missing", "damaged"):
        return ("This profile's lending record is missing or damaged, so it opens read only: a PC may hold the "
                "ledger. See Devices."), {}
    if node is None:
        return "", {}
    home = node.model
    if home.state is HomeState.AT_HOME:
        return "", {}
    if home.state is HomeState.NEEDS_REPAIR:
        return "The copy the PC handed back needs repair. Nothing was changed; it is read-only here.", {}
    borrower = node.store.peer(home.active.grant.borrower_id) if home.active is not None else None
    if home.state is HomeState.RETURN_RECEIVED:
        return ("{name} handed the ledger back. Checking it…", {"name": borrower.name}) if borrower else (
            "a PC handed the ledger back. Checking it…", {})
    return ("Lent to {name} · read only", {"name": borrower.name}) if borrower else ("Lent to a PC · read only", {})


# ==================================================================== moving a profile's home to the phone (task 17)

def _receive_move(devices: Devices, profile_root: Path, phone_name: str, message, source) -> tuple[str, str]:
    """On the phone: keep the arriving ledger as a new profile here and record this phone as its home, with the
    PC paired. The ledger stays locked until its owner unlocks it with the profile's password; the unlock checks
    it like any profile."""
    import os
    from lightning.security.keys import validate_key_file
    from lightning.sync.control import ControlStore, Peer, new_id
    from lightning.sync.copies import sha256_file
    from lightning.sync.domain import Compatibility
    from lightning.sync.service import copy_stream
    from lightning.sync.state import HomeProtocolModel
    from .paths import create_profile
    from .session import publish_keys

    try:
        key_file = json.loads(message.key_file)
        validate_key_file(key_file)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("BAD_REQUEST", "The profile's key file did not arrive intact.") from exc
    from lightning.sync.service import require_space
    profile_root.mkdir(parents=True, exist_ok=True)
    require_space(profile_root, message.size)
    identity = devices.identity(phone_name)
    paths = create_profile(message.profile_name, root=profile_root)
    paths.prepare()
    _drop_stale_arrivals(devices, message.profile_id)
    partial = paths.db_path.with_suffix(".part")
    try:
        with open(partial, "xb") as handle:
            copy_stream(source, handle, message.size)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(partial) != message.sha256:
            raise ProtocolError("BAD_REQUEST", "The ledger was damaged on the way. Nothing was kept; try again.")
        publish_keys(paths, key_file, replace=False)
        os.replace(partial, arriving_path(paths.db_path))
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    lineage = new_id()
    folder = devices.home_folder(paths)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    store = ControlStore(folder)
    store.create(HomeProtocolModel(
        profile_id=message.profile_id, home_id=identity.device_id, lineage_id=lineage, checkpoint_id=new_id(),
        checkpoint_sha256="0" * 64, compatibility=Compatibility(1, 1, message.ledger_schema, 1, message.key_id, 1),
        paired_devices={message.device_id}))
    store.save_peer(Peer(message.device_id, message.device_name, message.public_key, "", ""))
    (folder / HOME_META).write_text(json.dumps({"live_path": str(paths.db_path)}), encoding="utf-8")
    mark_lending(paths, message.profile_id)
    devices.last_arrival = Path(paths.db_path)
    return identity.device_id, lineage


def _drop_stale_arrivals(devices: Devices, profile_id: str) -> None:
    """The PC moves this profile again, so an earlier arrival it never confirmed is stale: remove it."""
    import shutil
    for node in devices.home_nodes():
        try:
            if node.live.exists() or node.profile_id != profile_id:
                continue
        except Exception:  # noqa: BLE001 - not this profile's record
            continue
        folder = node.checkpoints.parent
        with devices._lock:
            devices._nodes.pop(folder, None)
        shutil.rmtree(node.live.parent, ignore_errors=True)
        shutil.rmtree(folder, ignore_errors=True)


def open_move(devices: Devices, profile_root: Path, phone_name: str):
    """On the phone: show a code and wait for a PC to move a profile here."""
    devices.identity(phone_name)
    devices.ensure_listener()
    return devices.desk.open_move(lambda message, source: _receive_move(devices, Path(profile_root), phone_name,
                                                                        message, source), home_name=phone_name)


def move_to_phone(devices: Devices, *, paths: ProfilePaths, profile_id: str, name: str, key_id: str, schema: int,
                  address: str, code: str, pc_name: str):
    """On the PC, with the profile closed: send it to the phone, then keep this PC as a paired borrower. The
    PC's file is renamed first and stays as a backup (`<name>.moved-to-phone.db`), so there is never a second
    writable home; if the phone does not take it, the name is put back."""
    import os
    import shutil
    from lightning.sync.control import ControlStore, Peer
    from lightning.sync.state import BorrowerModel
    from lightning.sync.transport import move_profile
    from .paths import borrowed_profile

    identity = devices.identity(pc_name)
    live = Path(paths.db_path)
    moving = live.with_name(f"{live.stem}.moving.db")
    marker = Path(paths.data_dir) / MOVING_MARK
    marker.write_text(json.dumps({"profile_id": profile_id}), encoding="utf-8")
    os.rename(live, moving)
    try:
        moved = move_profile(address, code, identity, profile_id=profile_id, profile_name=name,
                             key_file=paths.keys_path.read_text(encoding="utf-8"), key_id=key_id,
                             ledger_schema=schema, ledger=str(moving))
    except BaseException:
        os.rename(moving, live)  # the phone keeps nothing it can open until this PC confirms (review H3)
        marker.unlink(missing_ok=True)
        raise
    borrowed = borrowed_profile(profile_id, root=devices.root)
    borrowed.prepare()
    shutil.copyfile(paths.keys_path, borrowed.keys_path)  # the same password opens it here
    (borrowed.data_dir / "profile.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    store = ControlStore(borrowed.data_dir)
    if store.role() is None:
        store.create(BorrowerModel(profile_id=profile_id, home_id=moved.done.home_id,
                                   lineage_id=moved.done.lineage_id, device_id=identity.device_id))
    store.save_peer(Peer(moved.done.home_id, moved.done.home_name, "", address.strip(), moved.fingerprint))
    os.rename(moving, live.with_name(f"{live.stem}.moved-to-phone.db"))
    marker.unlink(missing_ok=True)
    confirm_move(devices, BorrowerNode(borrowed))
    return moved


def confirm_move(devices: Devices, node: BorrowerNode) -> bool:
    """Tell the phone this PC kept the moved profile as a borrower: any authenticated request does. If the phone
    is out of reach now, the next Borrow does it."""
    from lightning.sync.domain import Status
    try:
        devices.link(node, timeout=STATUS_TIMEOUT).status(Status(node.model.device_id))
        return True
    except (LinkDown, ProtocolError, OSError):
        return False


def recover_moves(devices: Devices, profile_root: Path) -> None:
    """On the PC at start: finish a move cut off by a crash (review M10). With this PC's borrower record the
    phone has the ledger, so the PC's file stays a backup; without it the phone never kept it, so the file
    is this PC's profile again."""
    import os
    from .paths import borrowed_profile
    for marker in Path(profile_root).glob(f"*/{MOVING_MARK}"):
        try:
            profile_id = json.loads(marker.read_text(encoding="utf-8"))["profile_id"]
            folder = marker.parent
            live = folder / f"{folder.name}.db"
            moving = folder / f"{folder.name}.moving.db"
            if moving.exists():
                borrowed = borrowed_profile(profile_id, root=devices.root)
                kept = (borrowed.data_dir / "control.db").exists() and ControlStore(borrowed.data_dir).role()
                target = live.with_name(f"{folder.name}.moved-to-phone.db") if kept else live
                if not target.exists():
                    os.rename(moving, target)
            marker.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError):
            continue
