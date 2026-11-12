"""The encrypted local link between a PC and its phone (multiple devices, tasks 09 and 10).

The phone (home) listens on the local network over TLS 1.3 with its device certificate. A PC pins that
certificate's SHA-256 at pairing and refuses any other. Every connection starts with the phone's `Hello`
challenge; a paired PC answers with `Authenticate`, its signature over the challenge and the certificate it
sees, so a relay or a replayed answer fails. Then one request, one answer (plus the ledger bytes after
`Checkpoint` or `ReturnBegin`), and the connection closes.

Pairing is the one request without a signature: the phone shows two digits and the PC proves it has them, bit by
bit, in passkey-entry rounds bound to the certificate it sees (`identity.transcript`, `passkey`); the phone proves
the same back, and its reply is sealed with the key both sides then share, before the PC trusts the data key in it.
A failed or broken try gives the phone new digits.

Bounded everywhere: 16 KB per message, the declared file size, 30 s per read, four connections at once.
Nothing about the ledger is logged.
"""
from __future__ import annotations

import hashlib
import secrets
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import BinaryIO, Callable, Iterable

from .copies import CHUNK, CopyRejected
from .domain import (MAX_MESSAGE_BYTES, Accepted, Authenticate, BorrowActivated, BorrowCancel, BorrowGrant,
                     BorrowRequest, Cancelled, Checkpoint, Error, Hello, Message, MoveBegin, MoveDone, PairReply,
                     PairRequest, Prefetch,
                     Received, ReturnBegin, ReturnStatus, Status, StatusReply, decode_message, encode_message)
from .identity import DEFAULT_PORT, DeviceIdentity, transcript, verify_signature
from .passkey import (V2_MARKER, PasskeyMismatch, new_passkey, normalize_passkey, run_initiator, run_responder,
                      seal)
from .service import HomeNode, LinkDown, copy_stream
from .state import ProtocolError

TIMEOUT = 30
FIRST_TIMEOUT = 5        # seconds to finish the handshake and say who it is (review S1)
MAX_CONNECTIONS = 16
MAX_PER_ADDRESS = 4      # one device on the Wi-Fi cannot take every slot (review S1)
PAIRING_TOTAL = 20       # failed tries from all devices before pairing closes (review S2)
PAIRING_MINUTES = 10
PAIRING_TRIES = 3


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def move_transcript(request: MoveBegin, home_fingerprint: str) -> bytes:
    """A move's proof covers who sends, to which certificate, and exactly which ledger and key file."""
    key_file_hash = hashlib.sha256(request.key_file.encode("utf-8")).hexdigest()
    return transcript(request.pairing_id, home_fingerprint, request.device_id, request.public_key) + (
        f"\n{request.profile_id}\n{request.sha256}\n{request.size}\n{key_file_hash}\n{request.key_id}"
        f"\n{request.ledger_schema}").encode("ascii")


def _auth_data(nonce: str, home_fingerprint: str) -> bytes:
    return f"lightning-auth-v1\n{nonce}\n{home_fingerprint}".encode("ascii")


def _exact(stream, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        block = stream.recv(min(CHUNK, size - len(data)))
        if not block:
            raise ConnectionError("The connection closed early")
        data += block
    return bytes(data)


def send_message(stream, message: Message) -> None:
    data = encode_message(message)
    stream.sendall(len(data).to_bytes(4, "big") + data)


def receive_message(stream) -> Message:
    size = int.from_bytes(_exact(stream, 4), "big")
    if size > MAX_MESSAGE_BYTES:
        raise ProtocolError("BAD_REQUEST", "Message too large")
    return decode_message(_exact(stream, size))


class _SocketFile:
    """A socket read as a file of known length, for copy_stream."""

    def __init__(self, stream):
        self.stream = stream

    def read(self, size: int) -> bytes:
        return self.stream.recv(size)


def _send_file(stream, source: BinaryIO, size: int) -> None:
    left = size
    while left:
        block = source.read(min(CHUNK, left))
        if not block:
            raise ConnectionError("The file is shorter than declared")
        stream.sendall(block)
        left -= len(block)


# ==================================================================== the phone: pairing desk and server

@dataclass
class PendingPairing:
    node: HomeNode | None      # None while the phone waits for a PC to move a profile here
    code: str                  # the two digits the phone shows; new ones after every failed try
    home_name: str
    profile_name: str
    expires: float
    tries: int = 0             # failed tries from every address
    misses: dict = field(default_factory=dict)  # failed tries per address: three, then that address is refused
    busy: bool = False         # a try is under way (the rounds, or a move's file arriving)
    paired_name: str = ""      # set when a PC paired: what the phone shows
    digits: str = ""
    receive: Callable | None = None  # for a move: stores the ledger, returns (home_id, lineage_id)


class PairingDesk:
    """At most one open pairing on the phone, for ten minutes, one try at a time, three failed tries per PC, used once."""

    def __init__(self):
        self.pending: PendingPairing | None = None
        self._lock = threading.Lock()

    def open(self, node: HomeNode, *, home_name: str, profile_name: str) -> PendingPairing:
        with self._lock:
            self.pending = PendingPairing(node, new_passkey(), home_name, profile_name,
                                          time.monotonic() + PAIRING_MINUTES * 60)
            return self.pending

    def open_move(self, receive: Callable, *, home_name: str) -> PendingPairing:
        """Wait for a PC to move one of its profiles here (task 17). `receive(message, source)` keeps it."""
        with self._lock:
            self.pending = PendingPairing(None, new_passkey(), home_name, "",
                                          time.monotonic() + PAIRING_MINUTES * 60, receive=receive)
            return self.pending

    def close(self) -> None:
        with self._lock:
            self.pending = None

    def _begin(self, pending: PendingPairing | None, marker: str, address: str = "") -> str:
        """Under the lock: may this PC try now? Returns the digits for this try and marks the desk busy."""
        if marker != V2_MARKER:
            raise ProtocolError("PAIRING_FAILED", "Update Lightning on this PC to the phone's version, then pair again.")
        if pending is None or pending.paired_name or time.monotonic() >= pending.expires:
            raise ProtocolError("PAIRING_FAILED", "Open Pair a PC on the phone again and type the digits it shows.")
        if pending.busy:
            raise ProtocolError("PAIRING_FAILED", "The phone is pairing another device. Try again in a moment.")
        if pending.misses.get(address, 0) >= PAIRING_TRIES:
            raise ProtocolError("PAIRING_FAILED", "Three tries from this PC did not match. Open Pair a PC on the "
                                "phone again.")
        pending.busy = True
        return pending.code

    def _rounds(self, pending: PendingPairing, passkey: str, data: bytes, send, receive, address: str) -> bytes:
        """The passkey-entry rounds, without the lock. Any failure, a wrong bit or a dropped link, counts as a
        failed try and gives the phone new digits, so nothing a failed try revealed is ever used again."""
        try:
            return run_responder(send, receive, passkey, data)
        except BaseException as error:
            with self._lock:
                pending.busy = False
                self._wrong(pending, address)
            if isinstance(error, PasskeyMismatch):
                raise ProtocolError("PAIRING_FAILED", "Those digits are not the ones on the phone. The phone now "
                                    "shows new digits: type those.") from None
            raise

    def _wrong(self, pending: PendingPairing, address: str) -> None:
        """Failed tries count per address, so another device on the Wi-Fi cannot close the owner's pairing."""
        pending.misses[address] = pending.misses.get(address, 0) + 1
        pending.tries += 1
        pending.code = new_passkey()
        if pending.tries >= PAIRING_TOTAL and self.pending is pending:
            self.pending = None

    def handle_move(self, request: MoveBegin, home_fingerprint: str, source, address: str = "", *,
                    send: Callable = lambda message: None, receive: Callable = lambda: None) -> MoveDone:
        """Prove the digits, keep the ledger, and answer with this phone as its home. The desk is not held while the
        rounds run or the file arrives (review S3)."""
        with self._lock:
            pending = self.pending
            if pending is not None and pending.receive is None:
                raise ProtocolError("PAIRING_FAILED", "The phone is pairing a PC, not waiting for a profile. On the "
                                    "phone, choose Bring a profile from your PC.")
            passkey = self._begin(pending, request.proof, address)
        data = move_transcript(request, home_fingerprint)
        key = self._rounds(pending, passkey, data, send, receive, address)
        try:
            home_id, lineage_id = pending.receive(request, source)
        finally:
            pending.busy = False
        with self._lock:
            pending.paired_name, pending.profile_name, pending.digits = request.device_name, request.profile_name, passkey
            done_data = data + f"\n{home_id}\n{lineage_id}".encode("ascii")
            return MoveDone(request.pairing_id, home_id, pending.home_name, lineage_id, seal(key, "phone-move", done_data))

    def handle(self, request: PairRequest, home_fingerprint: str, address: str = "", *,
               send: Callable = lambda message: None, receive: Callable = lambda: None) -> PairReply:
        from .control import Peer
        with self._lock:
            pending = self.pending
            if pending is not None and pending.node is None:
                raise ProtocolError("PAIRING_FAILED", "The phone is waiting for a profile to move to it, not to pair. "
                                    "On the PC, unlock that profile and choose Profile settings, Move to your phone.")
            if pending is not None and pending.node.bridge.key() is None:
                raise ProtocolError("UNLOCK_NEEDED", "Unlock Lightning on your phone.")
            passkey = self._begin(pending, request.proof, address)
        data = transcript(request.pairing_id, home_fingerprint, request.device_id, request.public_key)
        key = self._rounds(pending, passkey, data, send, receive, address)
        with self._lock:
            pending.busy = False
            if self.pending is not pending or pending.paired_name:
                raise ProtocolError("PAIRING_FAILED", "Open Pair a PC on the phone again and type the digits it shows.")
            node = pending.node
            if node.bridge.key() is None:
                raise ProtocolError("UNLOCK_NEEDED", "Unlock Lightning on your phone.")
            node.pair(Peer(request.device_id, request.device_name, request.public_key, "", ""))
            home = node.model
            pending.paired_name, pending.digits = request.device_name, passkey
            key_file = (node.live.parent / "keys.json").read_text(encoding="utf-8")
            reply_data = data + f"\n{home.profile_id}\n{_digest(key_file)}".encode("ascii")
            return PairReply(request.pairing_id, home.profile_id, pending.profile_name, home.home_id,
                             pending.home_name, home.lineage_id, key_file, home.compatibility.key_id,
                             seal(key, "phone", reply_data))


class HomeServer:
    """Listens for paired PCs. `nodes` lists the home nodes this phone serves (one per profile)."""

    def __init__(self, identity: DeviceIdentity, nodes: Callable[[], Iterable[HomeNode]], desk: PairingDesk, *,
                 host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 on_authenticated: Callable[[HomeNode], None] | None = None,
                 arriving: Callable[[HomeNode], bool] = lambda node: False):
        self.identity, self.nodes, self.desk = identity, nodes, desk
        self.on_authenticated, self.arriving = on_authenticated, arriving
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_3
        identity.load_cert_chain(self.context)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.listener.bind((host, port))
            self.listener.listen(8)
        except OSError:
            self.listener.close()
            raise
        self.port = self.listener.getsockname()[1]
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._per_address: dict[str, int] = {}
        self._count_lock = threading.Lock()
        self._stopping = threading.Event()
        self.thread = threading.Thread(target=self._serve, name="lightning-sync-listener", daemon=True)

    def start(self) -> "HomeServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self._stopping.set()
        try:
            self.listener.shutdown(socket.SHUT_RDWR)  # wakes accept() on Linux and Android
        except OSError:
            pass
        self.listener.close()
        self.thread.join(5)

    def _serve(self) -> None:
        self.listener.settimeout(1.0)  # also notice stop() where shutdown does not wake accept()
        while not self._stopping.is_set():
            try:
                raw, peer_address = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            address = str(peer_address[0])
            with self._count_lock:
                crowded = self._per_address.get(address, 0) >= MAX_PER_ADDRESS
                if not crowded:
                    self._per_address[address] = self._per_address.get(address, 0) + 1
            if crowded:
                raw.close()
                continue
            if not self._slots.acquire(blocking=False):
                self._leave(address)
                raw.close()  # busy: the PC retries
                continue
            threading.Thread(target=self._connection, args=(raw, address), name="lightning-sync-peer",
                             daemon=True).start()

    def _leave(self, address: str) -> None:
        with self._count_lock:
            left = self._per_address.get(address, 1) - 1
            if left > 0:
                self._per_address[address] = left
            else:
                self._per_address.pop(address, None)

    def _node_for(self, device_id: str) -> HomeNode | None:
        """The profile this PC borrows. A profile still arriving by a move counts only when it is the PC's only
        one here: the PC that moved it confirms it by connecting (review H3)."""
        found = []
        for node in self.nodes():
            try:
                peer = node.store.peer(device_id)
                if peer is not None and not peer.revoked and device_id in node.model.paired_devices:
                    found.append(node)
            except Exception:  # noqa: BLE001 - one damaged record must not cut off the other profiles (review M9)
                continue
        settled = [node for node in found if not self.arriving(node)]
        return (settled or found or [None])[0]

    def _connection(self, raw: socket.socket, address: str = "") -> None:
        try:
            raw.settimeout(FIRST_TIMEOUT)  # a silent client lets its slot go quickly (review S1)
            with self.context.wrap_socket(raw, server_side=True) as stream:
                try:
                    self._exchange(stream, address)
                except ProtocolError as refused:
                    self._refuse(stream, Error(refused.code, str(refused)[:300]))
                except CopyRejected as rejected:
                    self._refuse(stream, Error("NEEDS_REPAIR", str(rejected)[:300]))
                except (ValueError, KeyError):
                    self._refuse(stream, Error("BAD_REQUEST", "The request was not understood."))
        except (OSError, ssl.SSLError, ConnectionError):
            pass  # the PC sees LinkDown and retries
        finally:
            raw.close()
            self._slots.release()
            self._leave(address)

    @staticmethod
    def _refuse(stream, error: Error) -> None:
        """Answer, then read what the PC is still sending before closing: closing with unread data resets
        the connection, and the PC would see "dropped" instead of the reason (seen on Windows)."""
        send_message(stream, error)
        stream.settimeout(2)
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline and stream.recv(CHUNK):
                pass
        except (OSError, ssl.SSLError):
            pass

    def _exchange(self, stream, address: str = "") -> None:
        nonce = secrets.token_hex(32)
        send_message(stream, Hello(nonce))
        first = receive_message(stream)
        stream.settimeout(TIMEOUT)
        rounds = dict(send=lambda message: send_message(stream, message), receive=lambda: receive_message(stream))
        if isinstance(first, PairRequest):
            send_message(stream, self.desk.handle(first, self.identity.fingerprint, address, **rounds))
            return
        if isinstance(first, MoveBegin):
            send_message(stream, self.desk.handle_move(first, self.identity.fingerprint, _SocketFile(stream),
                                                       address, **rounds))
            return
        if not isinstance(first, Authenticate):
            raise ProtocolError("UNAUTHORIZED", "Pair this PC first.")
        node = self._node_for(first.device_id)
        peer = node.store.peer(first.device_id) if node is not None else None
        if peer is None or not verify_signature(peer.public_key, _auth_data(nonce, self.identity.fingerprint),
                                                first.signature):
            raise ProtocolError("UNAUTHORIZED", "This PC is not paired with the phone.")
        device = first.device_id
        if self.on_authenticated is not None:
            self.on_authenticated(node)
        request = receive_message(stream)
        if isinstance(request, Status):
            send_message(stream, node.status(request, peer=device))
        elif isinstance(request, Prefetch):
            header, path = node.prefetch(request, peer=device)
            with open(path, "rb") as source:
                send_message(stream, header)
                _send_file(stream, source, header.size)
        elif isinstance(request, BorrowRequest):
            send_message(stream, node.borrow(request, peer=device))
        elif isinstance(request, BorrowActivated):
            send_message(stream, node.activate(request, peer=device))
        elif isinstance(request, BorrowCancel):
            send_message(stream, node.cancel(request, peer=device))
        elif isinstance(request, ReturnBegin):
            send_message(stream, node.receive_return(request, _SocketFile(stream), peer=device))
        elif isinstance(request, ReturnStatus):
            send_message(stream, node.return_status(request, peer=device))
        else:
            raise ProtocolError("BAD_REQUEST", "Unexpected request")


# ==================================================================== the PC: link and pairing

def _client_context() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # trust comes from the pinned fingerprint, checked below
    return context


def _split(endpoint: str) -> tuple[str, int]:
    host, _, port = endpoint.strip().rpartition(":")
    if not host:
        host, port = endpoint.strip(), str(DEFAULT_PORT)
    if not port.isdecimal() or not 0 < int(port) < 65536 or not host or len(host) > 253:
        raise ValueError("Type the phone's address as shown, like 192.168.1.20:47513.")
    return host.strip("[]"), int(port)


def _open(endpoint: str, timeout: float = TIMEOUT):
    host, port = _split(endpoint)
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        raise LinkDown("The phone did not answer. Open Lightning on it, on the same Wi-Fi.") from exc
    try:
        stream = _client_context().wrap_socket(raw)
    except (OSError, ssl.SSLError) as exc:
        raw.close()
        raise LinkDown("The phone did not answer securely.") from exc
    return stream


def _answer(stream, expected: type) -> Message:
    reply = receive_message(stream)
    if isinstance(reply, Error):
        raise ProtocolError(reply.code, reply.message)
    if not isinstance(reply, expected):
        raise ProtocolError("BAD_REQUEST", "The phone gave an unexpected answer.")
    return reply


@dataclass(frozen=True)
class Paired:
    reply: PairReply
    fingerprint: str
    digits: str


def _passkey_rounds(stream, passkey: str, data: bytes) -> bytes:
    """The PC's side of the rounds; the phone's refusal (an Error) reads as itself."""
    def receive():
        message = receive_message(stream)
        if isinstance(message, Error):
            raise ProtocolError(message.code, message.message)
        return message
    try:
        return run_initiator(lambda message: send_message(stream, message), receive, passkey, data)
    except PasskeyMismatch:
        raise ProtocolError("PAIRING_FAILED", "Those digits are not the ones on the phone. The phone now shows new "
                            "digits: type those.") from None


def pair(endpoint: str, code: str, identity: DeviceIdentity) -> Paired:
    """Pair this PC with the phone that shows the two digits `code`. The data key in the reply is trusted only
    after every round proved both sides hold the same digits for the same certificate."""
    code = normalize_passkey(code)
    stream = _open(endpoint)
    try:
        fingerprint = hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest()
        _answer(stream, Hello)
        import uuid
        pairing_id = str(uuid.uuid4())
        data = transcript(pairing_id, fingerprint, identity.device_id, identity.public_key)
        send_message(stream, PairRequest(pairing_id, identity.device_id, identity.name, identity.public_key, V2_MARKER))
        key = _passkey_rounds(stream, code, data)
        reply = _answer(stream, PairReply)
    except (OSError, ConnectionError) as exc:
        raise LinkDown("The connection to the phone dropped. Try again with the digits it shows.") from exc
    finally:
        stream.close()
    reply_data = data + f"\n{reply.profile_id}\n{_digest(reply.key_file)}".encode("ascii")
    if reply.pairing_id != pairing_id or not secrets.compare_digest(seal(key, "phone", reply_data), reply.proof):
        raise ProtocolError("PAIRING_FAILED", "The device that answered is not the phone showing these digits.")
    return Paired(reply, fingerprint, code)


@dataclass(frozen=True)
class Moved:
    done: MoveDone
    fingerprint: str
    digits: str


def move_profile(endpoint: str, code: str, identity: DeviceIdentity, *, profile_id: str, profile_name: str,
                 key_file: str, key_id: str, ledger_schema: int, ledger: str) -> Moved:
    """Send this PC's profile to the phone showing the two digits `code`. `ledger` is the closed encrypted database
    file. It is sent only after the rounds proved the phone holds the same digits for this certificate and file."""
    import os
    import uuid
    from .copies import sha256_file
    code = normalize_passkey(code)
    size, digest = os.path.getsize(ledger), sha256_file(ledger)
    stream = _open(endpoint)
    try:
        fingerprint = hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest()
        _answer(stream, Hello)
        request = MoveBegin(str(uuid.uuid4()), identity.device_id, identity.name, identity.public_key, profile_id,
                            profile_name, key_file, key_id, ledger_schema, digest, size, V2_MARKER)
        data = move_transcript(request, fingerprint)
        send_message(stream, request)
        key = _passkey_rounds(stream, code, data)
        with open(ledger, "rb") as source:
            _send_file(stream, source, size)
        done = _answer(stream, MoveDone)
    except (OSError, ConnectionError) as exc:
        raise LinkDown("The connection to the phone dropped. Nothing moved; try again.") from exc
    finally:
        stream.close()
    done_data = data + f"\n{done.home_id}\n{done.lineage_id}".encode("ascii")
    if done.pairing_id != request.pairing_id or not secrets.compare_digest(seal(key, "phone-move", done_data),
                                                                            done.proof):
        raise ProtocolError("PAIRING_FAILED", "The device that answered is not the phone showing these digits.")
    return Moved(done, fingerprint, code)


class TlsLink:
    """A paired PC's `Link` to its phone, pinned to the phone's certificate."""

    def __init__(self, endpoint: str, fingerprint: str, identity: DeviceIdentity):
        self.endpoint, self.fingerprint, self.identity = endpoint, fingerprint, identity
        self.timeout = TIMEOUT

    def _request(self, message: Message, expected: type | tuple, *, upload: tuple[BinaryIO, int] | None = None,
                 download: BinaryIO | None = None) -> Message:
        stream = _open(self.endpoint, self.timeout)
        try:
            seen = hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest()
            if not secrets.compare_digest(seen, self.fingerprint):
                raise ProtocolError("UNAUTHORIZED", "Another device answered at the phone's address.")
            hello = _answer(stream, Hello)
            send_message(stream, Authenticate(self.identity.device_id,
                                              self.identity.sign(_auth_data(hello.nonce, seen))))
            send_message(stream, message)
            if upload is not None:
                _send_file(stream, *upload)
            reply = _answer(stream, expected)
            if download is not None:
                copy_stream(_SocketFile(stream), download, reply.size)
            return reply
        except (OSError, ConnectionError) as exc:
            raise LinkDown("The connection to the phone dropped. It will try again.") from exc
        finally:
            stream.close()

    def status(self, message: Status) -> StatusReply:
        return self._request(message, StatusReply)

    def prefetch(self, message: Prefetch, sink: BinaryIO) -> Checkpoint:
        return self._request(message, Checkpoint, download=sink)

    def borrow(self, request: BorrowRequest) -> BorrowGrant:
        return self._request(request, BorrowGrant)

    def activate(self, message: BorrowActivated) -> BorrowGrant:
        return self._request(message, BorrowGrant)

    def cancel(self, message: BorrowCancel) -> Cancelled:
        return self._request(message, Cancelled)

    def send_return(self, begin: ReturnBegin, source: BinaryIO) -> Received | Accepted:
        return self._request(begin, (Received, Accepted), upload=(source, begin.candidate_size))

    def return_status(self, message: ReturnStatus) -> Received | Accepted:
        return self._request(message, (Received, Accepted))


__all__ = ["HomeServer", "Moved", "PairingDesk", "Paired", "TlsLink", "move_profile", "pair"]


# ==================================================================== the PC: keeping a pairing

def join_home(paired: Paired, *, endpoint: str, identity: DeviceIdentity, borrowed_profile, root=None):
    """Keep a new pairing on this PC: the borrowed profile's folder, the profile's key file (opened with the same
    password as on the phone), the phone's pinned certificate and address, and a borrower record. Returns its
    BorrowerNode. ``borrowed_profile`` is ``lightning.runtime.paths.borrowed_profile``, passed in because sync
    sits below runtime (9K)."""
    import json
    from lightning.security.keys import validate_key_file
    from .control import ControlStore, Peer
    from .service import BorrowerNode
    from .state import BorrowerModel

    reply = paired.reply
    try:
        validate_key_file(json.loads(reply.key_file))
    except (TypeError, ValueError) as exc:
        raise ProtocolError("PAIRING_FAILED", "The phone sent a damaged key file. Try again.") from exc
    paths = borrowed_profile(reply.profile_id, root=root)
    paths.prepare()
    slot = paths.keys_path.with_suffix(".part")
    slot.write_text(reply.key_file, encoding="utf-8")
    slot.replace(paths.keys_path)
    (paths.data_dir / "profile.json").write_text(json.dumps({"name": reply.profile_name}), encoding="utf-8")
    store = ControlStore(paths.data_dir)
    if store.role() is None:
        store.create(BorrowerModel(profile_id=reply.profile_id, home_id=reply.home_id, lineage_id=reply.lineage_id,
                                   device_id=identity.device_id))
    store.save_peer(Peer(reply.home_id, reply.home_name, "", endpoint, paired.fingerprint))
    return BorrowerNode(paths)


def link_to_home(node, identity: DeviceIdentity) -> TlsLink:
    """The pinned link to the phone this borrowed profile belongs to."""
    model = node.model
    home = node.store.peer(model.home_id)
    if home is None or home.revoked:
        raise ProtocolError("UNAUTHORIZED", "Pair this PC with the phone again.")
    return TlsLink(home.endpoint, home.certificate_sha256, identity)
