"""Bounded, versioned value objects for the first checkout protocol.

This is the in-process contract for task 05a. Transport authentication and
durable records arrive in later tasks; parsing these values never grants trust.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


PROTOCOL_VERSION = 1
CONTROL_SCHEMA_VERSION = 1
MAX_MESSAGE_BYTES = 16 * 1024
MAX_CANDIDATE_BYTES = 1024 * 1024 * 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_KEY_ID = re.compile(r"[0-9a-f]{16}\Z")
_HEX32 = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[^\x00-\x1f\x7f]{1,60}\Z")
_CODE = re.compile(r"[A-Z_]{3,40}\Z")


def _id(value: str, name: str) -> None:
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError(f"Invalid {name}")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError(f"Invalid {name}")


def _hash(value: str, name: str) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"Invalid {name}")


def _hex32(value: str, name: str) -> None:
    if not isinstance(value, str) or _HEX32.fullmatch(value) is None:
        raise ValueError(f"Invalid {name}")


def _name(value: str, name: str) -> None:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None or value != value.strip():
        raise ValueError(f"Invalid {name}")


def _natural(value: int, name: str, *, minimum: int = 0, maximum: int = 2**63 - 1) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {name}")


class MessageKind(StrEnum):
    BORROW_REQUEST = "BorrowRequest"
    BORROW_GRANT = "BorrowGrant"
    BORROW_ACTIVATED = "BorrowActivated"
    BORROW_CANCEL = "BorrowCancel"
    CANCELLED = "Cancelled"
    RETURN_BEGIN = "ReturnBegin"
    RECEIVED = "Received"
    ACCEPTED = "Accepted"
    PAIR_REQUEST = "PairRequest"
    PAIR_REPLY = "PairReply"
    PAIR_CONFIRM = "PairConfirm"
    STATUS = "Status"
    STATUS_REPLY = "StatusReply"
    PREFETCH = "Prefetch"
    CHECKPOINT = "Checkpoint"
    RETURN_STATUS = "ReturnStatus"
    ERROR = "Error"
    HELLO = "Hello"
    AUTHENTICATE = "Authenticate"
    MOVE_BEGIN = "MoveBegin"
    MOVE_DONE = "MoveDone"
    PASSKEY_COMMIT = "PasskeyCommit"
    PASSKEY_REVEAL = "PasskeyReveal"


@dataclass(frozen=True)
class Compatibility:
    protocol: int
    control_schema: int
    ledger_schema: int
    cipher_format: int
    key_id: str
    write_capability: int

    def __post_init__(self) -> None:
        for name in ("protocol", "control_schema", "ledger_schema", "cipher_format", "write_capability"):
            _natural(getattr(self, name), name, minimum=1, maximum=65535)
        if not isinstance(self.key_id, str) or _KEY_ID.fullmatch(self.key_id) is None:
            raise ValueError("Invalid key_id")

    def require_same(self, other: Compatibility) -> None:
        if self != other:
            raise ValueError("Incompatible protocol, schema, cipher, key or write capability")


@dataclass(frozen=True)
class BorrowRequest:
    operation_id: str
    checkout_id: str
    profile_id: str
    home_id: str
    lineage_id: str
    borrower_id: str
    base_checkpoint_id: str
    base_sha256: str
    compatibility: Compatibility

    def __post_init__(self) -> None:
        for name in ("operation_id", "checkout_id", "profile_id", "home_id", "lineage_id", "borrower_id", "base_checkpoint_id"):
            _id(getattr(self, name), name)
        _hash(self.base_sha256, "base_sha256")
        if not isinstance(self.compatibility, Compatibility):
            raise ValueError("Invalid compatibility")


@dataclass(frozen=True)
class BorrowGrant:
    checkout_id: str
    borrower_id: str
    lineage_id: str
    epoch: int
    base_checkpoint_id: str
    base_sha256: str

    def __post_init__(self) -> None:
        for name in ("checkout_id", "borrower_id", "lineage_id", "base_checkpoint_id"):
            _id(getattr(self, name), name)
        _natural(self.epoch, "epoch", minimum=1)
        _hash(self.base_sha256, "base_sha256")


@dataclass(frozen=True)
class BorrowActivated:
    operation_id: str
    checkout_id: str
    borrower_id: str
    epoch: int

    def __post_init__(self) -> None:
        for name in ("operation_id", "checkout_id", "borrower_id"):
            _id(getattr(self, name), name)
        _natural(self.epoch, "epoch", minimum=1)


@dataclass(frozen=True)
class BorrowCancel:
    operation_id: str
    checkout_id: str
    borrower_id: str
    never_activated: bool

    def __post_init__(self) -> None:
        for name in ("operation_id", "checkout_id", "borrower_id"):
            _id(getattr(self, name), name)
        if self.never_activated is not True:
            raise ValueError("Cancel requires the borrower's never-activated assertion")


@dataclass(frozen=True)
class Cancelled:
    checkout_id: str
    borrower_id: str
    epoch: int

    def __post_init__(self) -> None:
        _id(self.checkout_id, "checkout_id")
        _id(self.borrower_id, "borrower_id")
        _natural(self.epoch, "epoch")


@dataclass(frozen=True)
class ReturnBegin:
    operation_id: str
    return_id: str
    checkout_id: str
    borrower_id: str
    lineage_id: str
    epoch: int
    parent_checkpoint_id: str
    candidate_sha256: str
    candidate_size: int

    def __post_init__(self) -> None:
        for name in ("operation_id", "return_id", "checkout_id", "borrower_id", "lineage_id", "parent_checkpoint_id"):
            _id(getattr(self, name), name)
        _natural(self.epoch, "epoch", minimum=1)
        _hash(self.candidate_sha256, "candidate_sha256")
        _natural(self.candidate_size, "candidate_size", minimum=1, maximum=MAX_CANDIDATE_BYTES)


@dataclass(frozen=True)
class Received:
    return_id: str
    checkout_id: str
    candidate_sha256: str

    def __post_init__(self) -> None:
        _id(self.return_id, "return_id")
        _id(self.checkout_id, "checkout_id")
        _hash(self.candidate_sha256, "candidate_sha256")


@dataclass(frozen=True)
class Accepted:
    return_id: str
    checkout_id: str
    checkpoint_id: str
    candidate_sha256: str
    lineage_id: str
    epoch: int

    def __post_init__(self) -> None:
        for name in ("return_id", "checkout_id", "checkpoint_id", "lineage_id"):
            _id(getattr(self, name), name)
        _hash(self.candidate_sha256, "candidate_sha256")
        _natural(self.epoch, "epoch", minimum=1)


# ---------------------------------------------------------------- pairing, status and transfer (task 05a)
# Pairing runs over TLS to the phone's pinned-on-first-use certificate. Each side proves it knows the one-time
# pairing secret with an HMAC over both certificate fingerprints, so a relay that presents another certificate
# fails. PairReply carries the profile's key file, still locked by its password, only while the profile is
# unlocked on the phone; the PC opens the ledger with the same password.

@dataclass(frozen=True)
class PairRequest:
    pairing_id: str
    device_id: str
    device_name: str
    public_key: str        # ECDSA P-256, compressed point (33 bytes) as hex: verifies later connections
    proof: str             # HMAC-SHA256(secret, transcript) as hex

    def __post_init__(self) -> None:
        _id(self.pairing_id, "pairing_id")
        _id(self.device_id, "device_id")
        _name(self.device_name, "device_name")
        if (not isinstance(self.public_key, str) or len(self.public_key) != 66 or self.public_key[:2] not in ("02", "03")
                or any(c not in "0123456789abcdef" for c in self.public_key)):
            raise ValueError("Invalid public_key")
        _hex32(self.proof, "proof")


@dataclass(frozen=True)
class PairReply:
    pairing_id: str
    profile_id: str
    profile_name: str
    home_id: str
    home_name: str
    lineage_id: str
    key_file: str          # the profile's keys.json as JSON text, still locked: the PC opens it with the same password
    key_id: str
    proof: str

    def __post_init__(self) -> None:
        for name in ("pairing_id", "profile_id", "home_id", "lineage_id"):
            _id(getattr(self, name), name)
        _name(self.profile_name, "profile_name")
        _name(self.home_name, "home_name")
        if not isinstance(self.key_file, str) or not 2 <= len(self.key_file) <= 8000:
            raise ValueError("Invalid key_file")
        if not isinstance(self.key_id, str) or _KEY_ID.fullmatch(self.key_id) is None:
            raise ValueError("Invalid key_id")
        _hex32(self.proof, "proof")


@dataclass(frozen=True)
class PairConfirm:
    pairing_id: str
    device_id: str

    def __post_init__(self) -> None:
        _id(self.pairing_id, "pairing_id")
        _id(self.device_id, "device_id")


@dataclass(frozen=True)
class Status:
    device_id: str

    def __post_init__(self) -> None:
        _id(self.device_id, "device_id")


@dataclass(frozen=True)
class StatusReply:
    profile_id: str
    lineage_id: str
    state: str                     # a HomeState value
    checkpoint_id: str
    checkpoint_sha256: str
    epoch: int
    lent_to: str                   # device ID of the active borrower, or "" when none
    unlocked: bool

    def __post_init__(self) -> None:
        for name in ("profile_id", "lineage_id", "checkpoint_id"):
            _id(getattr(self, name), name)
        if self.state not in {"AT_HOME", "PREPARING_LEND", "LENT", "RETURN_RECEIVED", "PROMOTING", "NEEDS_REPAIR"}:
            raise ValueError("Invalid state")
        _hash(self.checkpoint_sha256, "checkpoint_sha256")
        _natural(self.epoch, "epoch")
        if self.lent_to:
            _id(self.lent_to, "lent_to")
        if type(self.unlocked) is not bool:
            raise ValueError("Invalid unlocked")


@dataclass(frozen=True)
class Prefetch:
    operation_id: str
    device_id: str

    def __post_init__(self) -> None:
        _id(self.operation_id, "operation_id")
        _id(self.device_id, "device_id")


@dataclass(frozen=True)
class Checkpoint:
    """Precedes exactly `size` bytes of the immutable encrypted checkpoint on the same stream."""
    checkpoint_id: str
    lineage_id: str
    sha256: str
    size: int
    ledger_schema: int

    def __post_init__(self) -> None:
        _id(self.checkpoint_id, "checkpoint_id")
        _id(self.lineage_id, "lineage_id")
        _hash(self.sha256, "sha256")
        _natural(self.size, "size", minimum=1, maximum=MAX_CANDIDATE_BYTES)
        _natural(self.ledger_schema, "ledger_schema", minimum=1, maximum=65535)


@dataclass(frozen=True)
class ReturnStatus:
    return_id: str
    device_id: str

    def __post_init__(self) -> None:
        _id(self.return_id, "return_id")
        _id(self.device_id, "device_id")


@dataclass(frozen=True)
class PasskeyCommit:
    """One round of two-digit pairing (`lightning.sync.passkey`): a commitment to one bit of the code."""
    index: int
    commitment: str

    def __post_init__(self) -> None:
        _natural(self.index, "index", maximum=6)
        _hex32(self.commitment, "commitment")


@dataclass(frozen=True)
class PasskeyReveal:
    """The nonce that opens the same round's commitment."""
    index: int
    nonce: str

    def __post_init__(self) -> None:
        _natural(self.index, "index", maximum=6)
        _hex32(self.nonce, "nonce")


@dataclass(frozen=True)
class Hello:
    """The home's first frame on every connection: a fresh challenge for the PC to sign."""
    nonce: str

    def __post_init__(self) -> None:
        _hex32(self.nonce, "nonce")


@dataclass(frozen=True)
class Authenticate:
    """A paired PC's answer: its ECDSA signature over the challenge and the home certificate it sees."""
    device_id: str
    signature: str

    def __post_init__(self) -> None:
        _id(self.device_id, "device_id")
        if (not isinstance(self.signature, str) or not 16 <= len(self.signature) <= 160
                or len(self.signature) % 2 or any(c not in "0123456789abcdef" for c in self.signature)):
            raise ValueError("Invalid signature")


@dataclass(frozen=True)
class MoveBegin:
    """A PC moves its profile's home to the phone (task 17). Exactly `size` bytes of the encrypted ledger follow.
    The key file travels as it is stored, still locked by the profile's password and recovery key."""
    pairing_id: str
    device_id: str
    device_name: str
    public_key: str
    profile_id: str
    profile_name: str
    key_file: str          # the profile's keys.json, as JSON text
    key_id: str
    ledger_schema: int
    sha256: str
    size: int
    proof: str             # HMAC with the phone's code over the transcript, the file's hash and the key file

    def __post_init__(self) -> None:
        for name in ("pairing_id", "device_id", "profile_id"):
            _id(getattr(self, name), name)
        _name(self.device_name, "device_name")
        _name(self.profile_name, "profile_name")
        if (not isinstance(self.public_key, str) or len(self.public_key) != 66 or self.public_key[:2] not in ("02", "03")
                or any(c not in "0123456789abcdef" for c in self.public_key)):
            raise ValueError("Invalid public_key")
        if not isinstance(self.key_file, str) or not 2 <= len(self.key_file) <= 8000:
            raise ValueError("Invalid key_file")
        if not isinstance(self.key_id, str) or _KEY_ID.fullmatch(self.key_id) is None:
            raise ValueError("Invalid key_id")
        _natural(self.ledger_schema, "ledger_schema", minimum=1, maximum=65535)
        _hash(self.sha256, "sha256")
        _natural(self.size, "size", minimum=1, maximum=MAX_CANDIDATE_BYTES)
        _hex32(self.proof, "proof")


@dataclass(frozen=True)
class MoveDone:
    """The phone kept the ledger and is its home now; the PC is paired with it."""
    pairing_id: str
    home_id: str
    home_name: str
    lineage_id: str
    proof: str

    def __post_init__(self) -> None:
        for name in ("pairing_id", "home_id", "lineage_id"):
            _id(getattr(self, name), name)
        _name(self.home_name, "home_name")
        _hex32(self.proof, "proof")


ERROR_CODES = frozenset({
    "UNAUTHORIZED", "REPLAY_CONFLICT", "STALE_AUTHORITY", "INCOMPATIBLE", "CANCELLED", "ALREADY_LENT",
    "STALE_BASE", "ACTIVE_CHECKOUT", "NOT_PUBLISHED", "UNLOCK_NEEDED", "UPDATE_NEEDED", "NO_SPACE",
    "NEEDS_REPAIR", "BAD_REQUEST", "PAIRING_FAILED", "UNKNOWN_RETURN", "BUSY",
})


@dataclass(frozen=True)
class Error:
    code: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or _CODE.fullmatch(self.code) is None or self.code not in ERROR_CODES:
            raise ValueError("Invalid error code")
        if not isinstance(self.message, str) or len(self.message) > 300:
            raise ValueError("Invalid error message")


Message = (BorrowRequest | BorrowGrant | BorrowActivated | BorrowCancel | Cancelled | ReturnBegin | Received | Accepted
           | PairRequest | PairReply | PairConfirm | Status | StatusReply | Prefetch | Checkpoint | ReturnStatus | Error
           | Hello | Authenticate | MoveBegin | MoveDone | PasskeyCommit | PasskeyReveal)
_TYPES: dict[MessageKind, type] = {
    MessageKind.BORROW_REQUEST: BorrowRequest,
    MessageKind.BORROW_GRANT: BorrowGrant,
    MessageKind.BORROW_ACTIVATED: BorrowActivated,
    MessageKind.BORROW_CANCEL: BorrowCancel,
    MessageKind.CANCELLED: Cancelled,
    MessageKind.RETURN_BEGIN: ReturnBegin,
    MessageKind.RECEIVED: Received,
    MessageKind.ACCEPTED: Accepted,
    MessageKind.PAIR_REQUEST: PairRequest,
    MessageKind.PAIR_REPLY: PairReply,
    MessageKind.PAIR_CONFIRM: PairConfirm,
    MessageKind.STATUS: Status,
    MessageKind.STATUS_REPLY: StatusReply,
    MessageKind.PREFETCH: Prefetch,
    MessageKind.CHECKPOINT: Checkpoint,
    MessageKind.RETURN_STATUS: ReturnStatus,
    MessageKind.ERROR: Error,
    MessageKind.HELLO: Hello,
    MessageKind.AUTHENTICATE: Authenticate,
    MessageKind.MOVE_BEGIN: MoveBegin,
    MessageKind.MOVE_DONE: MoveDone,
    MessageKind.PASSKEY_COMMIT: PasskeyCommit,
    MessageKind.PASSKEY_REVEAL: PasskeyReveal,
}
_KINDS = {value: key for key, value in _TYPES.items()}


def encode_message(message: Message) -> bytes:
    kind = _KINDS.get(type(message))
    if kind is None:
        raise ValueError("Unknown protocol message")
    data = {"kind": kind.value, "protocol": PROTOCOL_VERSION, **asdict(message)}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ValueError("Protocol message too large")
    return encoded


def decode_message(blob: bytes) -> Message:
    if not isinstance(blob, bytes) or len(blob) > MAX_MESSAGE_BYTES:
        raise ValueError("Protocol message too large or not bytes")
    try:
        def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate protocol JSON key")
                result[key] = value
            return result

        data: Any = json.loads(blob, object_pairs_hook=no_duplicates)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed protocol JSON") from exc
    if (not isinstance(data, dict) or type(data.get("protocol")) is not int
            or data["protocol"] != PROTOCOL_VERSION):
        raise ValueError("Unsupported protocol version")
    try:
        kind = MessageKind(data.pop("kind"))
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Unknown protocol message kind") from exc
    data.pop("protocol")
    cls = _TYPES[kind]
    return from_fields(cls, data)


def to_fields(message: Message) -> dict[str, Any]:
    """A message as a plain dict (no kind or protocol), e.g. to keep it in the control store."""
    return asdict(message)


def from_fields(cls: type, data: dict[str, Any]) -> Message:
    """Rebuild one message type from `to_fields` output, with the same strict schema as the wire."""
    data = dict(data)
    expected = set(cls.__dataclass_fields__)
    if set(data) != expected:
        raise ValueError("Protocol message fields do not match schema")
    if cls is BorrowRequest:
        compat = data["compatibility"]
        if not isinstance(compat, dict) or set(compat) != set(Compatibility.__dataclass_fields__):
            raise ValueError("Compatibility fields do not match schema")
        data["compatibility"] = Compatibility(**compat)
    return cls(**data)
