"""Lend and hand back with real encrypted files (multiple devices, tasks 07 and 08).

`HomeNode` runs on the device that holds the ledger (the phone). `BorrowerNode` runs on a paired PC. They talk
through a `Link`: in tests an in-process one, in the app the pinned TLS link of task 10. Every step that
changes who may write is recorded in the control store before anything acts on it (plan section 5):

    PC                                           home
    fetch: Prefetch ----------------------------> checkpoint the live ledger (unlocked only), send it
           verify the copy, record PREFETCHED
    borrow: record BORROW_PREPARED
           BorrowRequest -----------------------> close writes, check nothing changed since the checkpoint,
                                                  record LENT and the permit, reopen read-only
           record BORROWING, open working copy writable
    hand_back: record RETURNING (no more edits)
           ReturnBegin + the file --------------> store it, record Received; when unlocked: verify it, promote
                                                  it into place and record Accepted in one step, reopen writable
           record HANDED_BACK

A lost reply is answered by repeating the same request: the home returns what it stored. Nothing times out
into writing.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Protocol

from lightning.database.migrator import BUNDLED_LATEST_VERSION
from lightning.security.keys import key_id

from .control import ControlStore, Peer, new_id
from .copies import CHUNK, CopyRejected, content_fingerprint, fsync_file, sha256_file, verify_copy
from .domain import (MAX_CANDIDATE_BYTES, Accepted, BorrowActivated, BorrowCancel, BorrowGrant, BorrowRequest,
                     Cancelled, Checkpoint, Compatibility, Prefetch, Received, ReturnBegin, ReturnStatus, Status,
                     StatusReply)
from .state import BorrowerModel, BorrowerState, HomeProtocolModel, HomeState, ProtocolError

PROTOCOL = 1
CIPHER_FORMAT = 1          # SQLCipher 4 defaults
WRITE_CAPABILITY = 1
KEEP_CHECKPOINTS = 3
OWNER_WAIT = 2.0  # seconds an owner's button waits for a transfer to finish before saying "busy"


class LinkDown(ConnectionError):
    """The other device did not answer. Retry later; authority stays exactly as recorded."""


def compatibility(key: bytes, ledger_schema: int) -> Compatibility:
    return Compatibility(PROTOCOL, 1, ledger_schema, CIPHER_FORMAT, key_id(key), WRITE_CAPABILITY)


def derived_id(*parts: str) -> str:
    """A version 4 UUID fixed by its inputs, so a resumed step reuses the same ID."""
    return str(uuid.UUID(bytes=hashlib.sha256("\x00".join(parts).encode()).digest()[:16], version=4))


def copy_stream(source: BinaryIO, target: BinaryIO, size: int) -> None:
    left = size
    while left:
        block = source.read(min(CHUNK, left))
        if not block:
            raise ProtocolError("BAD_REQUEST", "The copy ended early")
        target.write(block)
        left -= len(block)


SPARE_BYTES = 64 * 1024 * 1024  # left free after a copy arrives, so the phone keeps working (review S3)


def require_space(folder: Path, size: int) -> None:
    """Refuse a copy the device has no room for, before any byte is written."""
    if shutil.disk_usage(folder).free < size + SPARE_BYTES:
        raise ProtocolError("NO_SPACE", "The phone does not have enough free space for the profile. Free some "
                            "space on it and try again.")


def promotion_files(folder: Path):
    """This platform's durable file adapter for promotion (lightning.database.promotion)."""
    if os.name == "nt":
        from lightning.database.promotion_windows import WindowsPromotionFileOps
        return WindowsPromotionFileOps(folder)
    from lightning.database.promotion import PosixPromotionFileOps
    return PosixPromotionFileOps(folder)


# ==================================================================== home (the phone)

class HomeBridge(Protocol):
    """What the home node needs from the app that holds the profile open."""

    def key(self) -> bytes | None:
        """A copy of the data key while the profile is unlocked, else None."""

    def set_mode(self, mode: str) -> None:
        """"home" (writable), "reader" (read-only connection) or "closed" (no finance connection). Changing
        mode drains requests first, so no write is in flight afterwards."""


class HomeNode:
    """One profile on the device that holds it. Calls come from the transport thread, one at a time."""

    def __init__(self, *, live_path: str | Path, control_folder: str | Path, bridge: HomeBridge):
        self.live = Path(live_path)
        self.store = ControlStore(control_folder)
        self.checkpoints = Path(control_folder) / "checkpoints"
        self.checkpoints.mkdir(mode=0o700, exist_ok=True)
        self.bridge = bridge
        self._lock = threading.RLock()

    # ------------------------------------------------------------ setup (owning thread, profile unlocked)
    @classmethod
    def enable(cls, db, *, live_path: str | Path, control_folder: str | Path, home_id: str,
               bridge: HomeBridge) -> "HomeNode":
        """First pairing: give the ledger its stable ID and this device its home record. Idempotent. `db` is
        the open writable finance Database; this runs on its owning thread."""
        node = cls(live_path=live_path, control_folder=control_folder, bridge=bridge)
        if node.store.role() == "home":
            return node
        from .copies import ensure_profile_id, schema_version
        profile_id = ensure_profile_id(db)
        key = db.copy_key()
        node.store.create(HomeProtocolModel(
            profile_id=profile_id, home_id=home_id, lineage_id=new_id(), checkpoint_id=new_id(),
            checkpoint_sha256="0" * 64, compatibility=compatibility(key, schema_version(db)), paired_devices=set()))
        return node

    @property
    def model(self) -> HomeProtocolModel:
        return self.store.read("home")

    @property
    def profile_id(self) -> str:
        return self.model.profile_id

    def _key(self) -> bytes:
        key = self.bridge.key()
        if key is None:
            raise ProtocolError("UNLOCK_NEEDED", "Unlock Lightning on your phone.")
        return key

    def _checkpoint_path(self, checkpoint_id: str) -> Path:
        return self.checkpoints / f"{checkpoint_id}.db"

    def _require_paired(self, peer: str) -> None:
        if peer not in self.model.paired_devices:
            raise ProtocolError("UNAUTHORIZED", "This PC is not paired with this profile.")

    def _dry_run(self, change: Callable[[HomeProtocolModel], object]) -> None:
        """Check a request against a throwaway copy of the record before closing anything."""
        change(HomeProtocolModel.from_record(self.model.to_record()))

    # ------------------------------------------------------------ pairing records
    def pair(self, peer: Peer) -> None:
        with self._lock:
            self.store.save_peer(peer)
            self.store.home(lambda home: home.pair(peer.device_id))

    @contextmanager
    def _owner_step(self) -> Iterator[None]:
        """The owner's buttons wait at most a moment for a transfer in progress, never minutes (review M8)."""
        if not self._lock.acquire(timeout=OWNER_WAIT):
            raise ProtocolError("BUSY", "A PC is sending or fetching the profile right now. Try again in a minute.")
        try:
            yield
        finally:
            self._lock.release()

    def revoke(self, device_id: str) -> None:
        with self._owner_step():
            peer = self.store.peer(device_id)
            if peer is not None:
                self.store.save_peer(Peer(peer.device_id, peer.name, peer.public_key, peer.endpoint,
                                          peer.certificate_sha256, revoked=True))
            self.store.home(lambda home: home.revoke(device_id))

    # ------------------------------------------------------------ requests from a PC
    def status(self, message: Status, *, peer: str) -> StatusReply:
        with self._lock:
            self._require_paired(peer)
            home = self.model
            lent_to = home.active.grant.borrower_id if home.active is not None else ""
            sha = home.checkpoint_sha256
            return StatusReply(home.profile_id, home.lineage_id, home.state.value, home.checkpoint_id,
                               sha, home.epoch, lent_to, self.bridge.key() is not None)

    def prefetch(self, message: Prefetch, *, peer: str) -> tuple[Checkpoint, Path]:
        """A fresh immutable checkpoint of the live ledger, or the active borrower's base again after a crash."""
        with self._lock:
            self._require_paired(peer)
            home = self.model
            if home.state is not HomeState.AT_HOME:
                if home.active is not None and home.active.grant.borrower_id == peer:
                    path = self._checkpoint_path(home.active.grant.base_checkpoint_id)
                    return Checkpoint(home.active.grant.base_checkpoint_id, home.lineage_id,
                                      home.active.grant.base_sha256, path.stat().st_size,
                                      home.compatibility.ledger_schema), path
                holder = self.store.peer(home.active.grant.borrower_id) if home.active is not None else None
                raise ProtocolError("ALREADY_LENT", f"The profile is lent to {holder.name}." if holder else
                                    "The profile is lent to another PC.")
            key = self._key()
            from lightning.database.connection import Database
            from lightning.database.snapshot import export_snapshot
            from .copies import schema_version
            checkpoint_id = new_id()
            path = self._checkpoint_path(checkpoint_id)
            source = Database(self.live, key=key)  # reads only; the export is one consistent transaction
            try:
                export_snapshot(source.conn, path, key=key, source_encrypted=True)
                schema = schema_version(source)
            finally:
                source.close()
            sha = sha256_file(path)
            current = compatibility(key, schema)

            def record(home: HomeProtocolModel) -> None:
                home.set_checkpoint(checkpoint_id, sha)
                home.compatibility = current
            self.store.home(record)
            self._prune_checkpoints()
            return Checkpoint(checkpoint_id, home.lineage_id, sha, path.stat().st_size, schema), path

    def _prune_checkpoints(self) -> None:
        home = self.model
        keep = {home.checkpoint_id}
        if home.active is not None:
            keep.add(home.active.grant.base_checkpoint_id)
        files = sorted(self.checkpoints.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[KEEP_CHECKPOINTS:]:
            if path.stem not in keep:
                path.unlink(missing_ok=True)

    def borrow(self, request: BorrowRequest, *, peer: str) -> BorrowGrant:
        with self._lock:
            home = self.model
            if request.checkout_id in {c.grant.checkout_id for c in [home.active] if c is not None} \
                    or home.state is not HomeState.AT_HOME:
                return self.store.home(lambda h: h.borrow(request, authenticated_peer=peer))  # replay or refusal
            if self.store.unresolved_promotion() is not None:  # review M5: still taking in the last copy
                raise ProtocolError("BUSY", "The phone is still taking in the last copy. Try again in a minute.")
            self._dry_run(lambda h: h.borrow(request, authenticated_peer=peer))
            key = self._key()
            base = self._checkpoint_path(request.base_checkpoint_id)
            self.bridge.set_mode("reader")  # drains; from here the phone cannot write
            try:
                if content_fingerprint(self.live, key) != content_fingerprint(base, key):
                    raise ProtocolError("STALE_BASE", "The phone changed since the copy was taken. Fetching again.")
                self.store.rebase_accepted(request.base_checkpoint_id, sha256_file(self.live))
                return self.store.home(lambda h: h.borrow(request, authenticated_peer=peer))
            except BaseException:
                self.bridge.set_mode("home" if self.writable() else "reader")
                raise

    def activate(self, message: BorrowActivated, *, peer: str) -> BorrowGrant:
        with self._lock:
            return self.store.home(lambda h: h.activate(message, authenticated_peer=peer))

    def cancel(self, message: BorrowCancel, *, peer: str) -> Cancelled:
        with self._lock:
            was_lent = self.model.state is HomeState.LENT
            receipt = self.store.home(lambda h: h.cancel(message, authenticated_peer=peer))
            if was_lent and self.writable() and self.bridge.key() is not None:
                self.bridge.set_mode("home")
            return receipt

    def _incoming(self, return_id: str) -> Path:
        return self.live.with_name(f"{self.live.stem}.incoming-{return_id}.db")

    def receive_return(self, begin: ReturnBegin, source: BinaryIO, *, peer: str) -> Received | Accepted:
        """Store the final copy, record Received, and accept it now if the phone is unlocked."""
        with self._lock:
            known = self.model.receipt_for(begin.return_id)
            if known is not None:
                with open(os.devnull, "wb") as discard:
                    copy_stream(source, discard, begin.candidate_size)
                return self.store.home(lambda h: h.receive_return(begin, authenticated_peer=peer))
            self._dry_run(lambda h: h.receive_return(begin, authenticated_peer=peer))
            require_space(self.live.parent, begin.candidate_size)
            target = self._incoming(begin.return_id)
            partial = target.with_suffix(".part")
            partial.unlink(missing_ok=True)
            try:
                with open(partial, "xb") as handle:
                    copy_stream(source, handle, begin.candidate_size)
                    handle.flush()
                    os.fsync(handle.fileno())
                if sha256_file(partial) != begin.candidate_sha256:
                    raise ProtocolError("BAD_REQUEST", "The copy was damaged on the way. Sending again.")
                os.replace(partial, target)
            except BaseException:
                partial.unlink(missing_ok=True)
                raise
            receipt = self.store.home(lambda h: h.receive_return(begin, authenticated_peer=peer))
            if self.bridge.key() is not None:
                return self.accept_pending() or receipt
            return receipt

    def return_status(self, message: ReturnStatus, *, peer: str) -> Received | Accepted:
        with self._lock:
            self._require_paired(peer)
            home = self.model
            receipt = home.receipt_for(message.return_id)
            if receipt is None:
                raise ProtocolError("UNKNOWN_RETURN", "The phone has not received that copy.")
            pending = home.pending_return()
            if isinstance(receipt, Received) and (pending is None or pending.return_id != message.return_id):
                raise ProtocolError("STALE_AUTHORITY", "The phone took the profile back; this copy will not go in.")
            return receipt

    # ------------------------------------------------------------ the home's own steps
    @contextmanager
    def _offline(self) -> Iterator[None]:
        """No finance connection during promotion; afterwards writable only if the ledger is home again."""
        self.bridge.set_mode("closed")
        try:
            yield
        finally:
            home = self.model
            at_home = home.state is HomeState.AT_HOME and self.store.unresolved_promotion() is None
            if self.bridge.key() is not None:
                self.bridge.set_mode("home" if at_home else "reader")

    def accept_pending(self) -> Accepted | None:
        """Verify and promote the received copy (plan section 9). Called on receipt and on every unlock.
        A copy that fails verification leaves the ledger at NEEDS_REPAIR, with every file kept."""
        from lightning.database.promotion import CandidatePromotionService, PromotionBlocked
        with self._lock:
            home = self.model
            pending = home.pending_return()
            key = self.bridge.key()
            if pending is None or key is None:
                return None
            if home.state is HomeState.NEEDS_REPAIR:
                raise ProtocolError("NEEDS_REPAIR", "The returned copy needs repair before the phone can use it.")
            candidate = self._incoming(pending.return_id)
            try:
                if not candidate.exists() or sha256_file(candidate) != pending.candidate_sha256:
                    raise CopyRejected("The returned copy is missing or changed on this phone.")
                verify_copy(candidate, key, home.profile_id, schema=home.compatibility.ledger_schema)
            except CopyRejected:
                self.store.home(lambda h: h.mark_needs_repair())
                raise
            accepted = self.store.read_state().accepted
            new_checkpoint = derived_id("accepted", pending.return_id)
            # The accepted copy is also the checkpoint a PC fetches next; copied while it is still immutable.
            checkpoint = self._checkpoint_path(new_checkpoint)
            if not checkpoint.exists():
                shutil.copyfile(candidate, checkpoint)
            try:
                with promotion_files(self.live.parent) as files:
                    CandidatePromotionService(files, self.store).promote(
                        operation_id=derived_id("promote", pending.return_id),
                        old_checkpoint_id=accepted.checkpoint_id, new_checkpoint_id=new_checkpoint,
                        live_name=self.live.name, candidate_name=candidate.name,
                        previous_name=f"{self.live.stem}.before-{pending.return_id}.db",
                        operation_gate=self._offline(),
                        verify_database=lambda name: verify_copy(self.live.parent / name, key, home.profile_id),
                        activate=lambda checkpoint, name: None)
            except PromotionBlocked:
                if self.store.unresolved_promotion() is None:  # refused before it began: never retry (review L11)
                    self.store.home(lambda h: h.mark_needs_repair())
                raise
            self._prune_previous()
            return self.model.receipt_for(pending.return_id)

    def recover(self) -> None:
        """At unlock: finish an interrupted promotion, then accept a copy that arrived while locked."""
        from lightning.database.promotion import CandidatePromotionService
        with self._lock:
            if self.store.unresolved_promotion() is not None:
                key = self._key()
                profile_id = self.profile_id
                with promotion_files(self.live.parent) as files:
                    CandidatePromotionService(files, self.store).recover(
                        live_name=self.live.name, operation_gate=self._offline(),
                        verify_database=lambda name: verify_copy(self.live.parent / name, key, profile_id),
                        activate=lambda checkpoint, name: None)
            self.accept_pending()

    def _prune_previous(self) -> None:
        """Keep the last few ledgers replaced by a hand-back, as backups; older ones go (review L12)."""
        previous = sorted(self.live.parent.glob(f"{self.live.stem}.before-*.db"), key=lambda p: p.stat().st_mtime,
                          reverse=True)
        for path in previous[KEEP_CHECKPOINTS:]:
            path.unlink(missing_ok=True)

    def writable(self) -> bool:
        """Whether the home may open its ledger for writing now."""
        return self.model.state is HomeState.AT_HOME and self.store.unresolved_promotion() is None

    def take_back(self, *, reopen: bool = True) -> None:
        """Owner's choice when the PC is lost: the phone's last accepted copy becomes the ledger again under a
        new lineage. That PC's later edits can never come back in (plan section 10). `reopen=False` when the
        caller already holds the request gate and reopens the session itself."""
        with self._owner_step():
            if self.store.unresolved_promotion() is not None:
                raise ProtocolError("BUSY", "The phone is taking in the PC's copy. Lock and unlock Lightning to "
                                    "finish, then the profile is home with the PC's changes.")
            if self.model.state is not HomeState.NEEDS_REPAIR and self.model.pending_return() is not None:
                raise ProtocolError("BUSY", "The PC's copy has arrived. Unlock Lightning on this phone to take it in; "
                                    "no need to take the profile back.")
            self.store.home(lambda h: h.take_back(new_id()))
            if reopen and self.bridge.key() is not None:
                self.bridge.set_mode("home")


# ==================================================================== borrower (a PC)

class Link(Protocol):
    """How a PC reaches its home. Each call raises LinkDown when the home does not answer and ProtocolError
    for a refusal."""

    def status(self, message: Status) -> StatusReply: ...
    def prefetch(self, message: Prefetch, sink: BinaryIO) -> Checkpoint: ...
    def borrow(self, request: BorrowRequest) -> BorrowGrant: ...
    def activate(self, message: BorrowActivated) -> BorrowGrant: ...
    def cancel(self, message: BorrowCancel) -> Cancelled: ...
    def send_return(self, begin: ReturnBegin, source: BinaryIO) -> Received | Accepted: ...
    def return_status(self, message: ReturnStatus) -> Received | Accepted: ...


class BorrowerNode:
    """One borrowed profile on this PC (`BorrowedPaths`). The caller closes the working copy before
    `hand_back` and opens it writable only while `writable` is true."""

    def __init__(self, paths):
        self.paths = paths
        self.store = ControlStore(paths.data_dir)
        self._lock = threading.RLock()

    @property
    def model(self) -> BorrowerModel:
        return self.store.read("borrower")

    @property
    def writable(self) -> bool:
        return self.model.writable

    def _prefetch_path(self, checkpoint_id: str) -> Path:
        return self.paths.prefetch_dir / f"{checkpoint_id}.db"

    def _candidate_path(self, return_id: str) -> Path:
        return self.paths.sealed_dir / f"{return_id}.db"

    def fetch(self, link: Link, key: bytes) -> Checkpoint:
        """Download the home's current checkpoint and verify it. Never replaces a lend in progress."""
        with self._lock:
            pc = self.model
            if pc.state not in (BorrowerState.HANDED_BACK, BorrowerState.ABORTED, BorrowerState.PREFETCHED):
                raise ProtocolError("STALE_AUTHORITY", "This PC already holds the profile.")
            reply = link.status(Status(pc.device_id))
            if reply.lineage_id != pc.lineage_id:  # taken back or kept again on the phone: follow it
                pc = self.store.borrower(lambda m: (m.adopt_lineage(reply.lineage_id), m)[1])
            partial = self.paths.prefetch_dir / f"incoming-{new_id()}.part"
            try:
                with open(partial, "xb") as sink:
                    header = link.prefetch(Prefetch(new_id(), pc.device_id), sink)
                    sink.flush()
                    os.fsync(sink.fileno())
                if partial.stat().st_size != header.size or sha256_file(partial) != header.sha256:
                    raise CopyRejected("The copy was damaged on the way. Try again.")
                verify_copy(partial, key, pc.profile_id, schema=BUNDLED_LATEST_VERSION)
                target = self._prefetch_path(header.checkpoint_id)
                os.replace(partial, target)
            finally:
                partial.unlink(missing_ok=True)
            self.store.borrower(lambda m: m.prefetched(header.checkpoint_id, header.sha256))
            for old in self.paths.prefetch_dir.glob("*.db"):
                if old != target:
                    old.unlink(missing_ok=True)
            return header

    def borrow(self, link: Link, key: bytes) -> BorrowGrant:
        """Ask for the permit for the fetched copy; on a grant, the working copy becomes writable here."""
        with self._lock:
            pc = self.model
            if pc.state is BorrowerState.BORROWING:
                return pc.grant
            if pc.state is BorrowerState.PREFETCHED:
                request = BorrowRequest(new_id(), new_id(), pc.profile_id, pc.home_id, pc.lineage_id, pc.device_id,
                                        pc.checkpoint_id, pc.checkpoint_sha256,
                                        compatibility(key, BUNDLED_LATEST_VERSION))
                self.store.borrower(lambda m: m.prepare(request))
            elif pc.state is BorrowerState.BORROW_PREPARED:
                request = pc.request  # retry the same request after a lost reply
            else:
                raise ProtocolError("STALE_AUTHORITY", "Fetch the phone's copy first.")
            try:
                grant = link.borrow(request)
            except ProtocolError as refused:
                if refused.code in ("STALE_BASE", "ALREADY_LENT", "INCOMPATIBLE", "STALE_AUTHORITY"):
                    self._abort(link, request)  # never writable, so it can be cancelled cleanly
                raise
            working = self.paths.working_path
            partial = working.with_suffix(".part")
            shutil.copyfile(self._prefetch_path(request.base_checkpoint_id), partial)
            fsync_file(partial)
            os.replace(partial, working)
            self.store.borrower(lambda m: m.granted(grant))
            try:
                link.activate(BorrowActivated(new_id(), grant.checkout_id, pc.device_id, grant.epoch))
            except (LinkDown, ProtocolError):
                pass  # advisory: the home is already lent to this PC
            return grant

    def _abort(self, link: Link, request: BorrowRequest) -> None:
        cancel = BorrowCancel(new_id(), request.checkout_id, request.borrower_id, True)
        self.store.borrower(lambda m: m.abort(cancel))
        try:
            link.cancel(cancel)
        except (LinkDown, ProtocolError):
            pass  # the tombstone is sent again with the next status check

    def cancel(self, link: Link) -> None:
        """Give up a request that never became writable."""
        with self._lock:
            pc = self.model
            if pc.state is BorrowerState.BORROW_PREPARED:
                self._abort(link, pc.request)
            elif pc.state is BorrowerState.ABORTED and pc.cancel is not None:
                link.cancel(pc.cancel)

    def seal(self) -> None:
        """The phone is out of reach at close: keep the lend; hand back later from this same copy."""
        with self._lock:
            if self.model.state is BorrowerState.BORROWING:
                self.store.borrower(lambda m: m.seal())

    def start_over(self) -> Path | None:
        """The phone took the ledger back: keep this PC's copy as a backup beside it and borrow afresh next.
        Returns the backup's path."""
        with self._lock:
            working = self.paths.working_path
            kept = None
            if working.exists():
                kept = working.with_name(f"{working.stem}.taken-back-{new_id()[:8]}.db")
                os.replace(working, kept)
            self.store.borrower(lambda m: m.start_over())
            return kept

    def reopen(self) -> None:
        """Opening Lightning again before the sealed copy went home: keep editing."""
        with self._lock:
            if self.model.state is BorrowerState.SEALED:
                self.store.borrower(lambda m: m.unseal())

    def hand_back(self, link: Link) -> Received | Accepted:
        """Freeze the working copy and send it home. The working copy is closed by the caller and stays
        read-only from here, whatever the phone answers (rule 4)."""
        with self._lock:
            pc = self.model
            if pc.state in (BorrowerState.BORROWING, BorrowerState.SEALED):
                return_id = new_id()
                candidate = self._candidate_path(return_id)
                shutil.copyfile(self.paths.working_path, candidate)
                fsync_file(candidate)
                size = candidate.stat().st_size
                if size > MAX_CANDIDATE_BYTES:
                    raise ProtocolError("NO_SPACE", "The profile is too large to hand back.")
                grant = pc.grant
                begin = ReturnBegin(new_id(), return_id, grant.checkout_id, pc.device_id, grant.lineage_id,
                                    grant.epoch, grant.base_checkpoint_id, sha256_file(candidate), size)
                self.store.borrower(lambda m: m.begin_return(begin))
            elif pc.state is BorrowerState.RETURNING:
                begin = pc.returning
            else:
                raise ProtocolError("STALE_AUTHORITY", "This PC does not hold the profile.")
            try:
                with open(self._candidate_path(begin.return_id), "rb") as source:
                    receipt = link.send_return(begin, source)
            except ProtocolError as refused:
                if refused.code == "STALE_AUTHORITY":
                    self.store.borrower(lambda m: m.needs_repair())  # taken back meanwhile: keep this copy
                raise
            return self._settle(receipt)

    def check_return(self, link: Link) -> Received | Accepted | None:
        """While RETURNING: ask whether the phone accepted the copy (it waits for its own unlock)."""
        with self._lock:
            pc = self.model
            if pc.state is not BorrowerState.RETURNING:
                return pc.accepted
            try:
                receipt = link.return_status(ReturnStatus(pc.returning.return_id, pc.device_id))
            except ProtocolError as refused:
                if refused.code == "UNKNOWN_RETURN":
                    return self.hand_back(link)  # the copy never arrived: send it again
                if refused.code == "STALE_AUTHORITY":
                    self.store.borrower(lambda m: m.needs_repair())  # taken back meanwhile: keep this copy
                raise
            return self._settle(receipt)

    def _settle(self, receipt: Received | Accepted) -> Received | Accepted:
        if isinstance(receipt, Accepted):
            self.store.borrower(lambda m: m.handed_back(receipt))
        return receipt
