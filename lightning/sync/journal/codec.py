"""Bounded, canonical v2 laboratory messages. v1 and its fixtures stay frozen."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lightning.sync.identity import verify_signature

MAX_MESSAGE = 64 * 1024
ZERO_HASH = "0" * 64
GROUP = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")


class JournalError(ValueError):
    """A refused protocol operation; contains no financial payload."""


def _tree(value, depth=0):
    if depth > 12:
        raise JournalError("Message nesting limit exceeded")
    if value is None or type(value) is bool:
        return
    if type(value) is int and -(2**53) < value < 2**53:
        return
    if type(value) is str:
        if len(value) > 16384:
            raise JournalError("Text limit exceeded")
        try:
            value.encode("utf-8")
        except UnicodeError as error:
            raise JournalError("Invalid Unicode") from error
        return
    if type(value) is list and len(value) <= 256:
        for item in value:
            _tree(item, depth + 1)
        return
    if type(value) is dict and len(value) <= 256 and all(type(k) is str for k in value):
        for key, item in value.items():
            _tree(key, depth + 1)
            _tree(item, depth + 1)
        return
    raise JournalError("Unsupported value or collection size")


def canonical(value) -> bytes:
    _tree(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def fields(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise JournalError("Unknown or missing message fields")


def uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise JournalError("Invalid UUID") from error


def number(value, *, minimum=0):
    if type(value) is not int or not minimum <= value < 2**53:
        raise JournalError("Invalid sequence or revision")


def hash_value(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise JournalError("Invalid digest")


def origin(value):
    fields(value, ("device", "incarnation", "seq"))
    uuid(value["device"])
    uuid(value["incarnation"])
    number(value["seq"], minimum=1)


def origin_id(value):
    origin(value)
    return f'{value["device"]}/{value["incarnation"]}/{value["seq"]}'


def proposal(value):
    fields(value, ("version", "type", "profile", "generation", "origin", "kind", "kind_version", "record",
                   "groups", "bases", "dependencies", "cursor", "created_at", "display_zone"))
    if type(value["version"]) is not int or value["version"] != 2 or value["type"] != "proposal":
        raise JournalError("Unsupported protocol")
    uuid(value["profile"])
    uuid(value["generation"])
    uuid(value["record"])
    origin(value["origin"])
    if type(value["kind"]) is not str or value["kind"] not in {"dummy.add", "dummy.edit", "dummy.delete", "transaction.add", "transaction.edit", "transaction.delete", "action.add"}:
        raise JournalError("Unsupported entry kind; update the device or home")
    if type(value["kind_version"]) is not int or value["kind_version"] not in ((1, 2) if value['kind'] == 'action.add' else (1,)):
        raise JournalError("Unsupported entry version; update the device or home")
    try:
        if type(value["created_at"]) is not str or len(value["created_at"]) > 40:
            raise ValueError
        if datetime.fromisoformat(value["created_at"]).utcoffset() is None:
            raise ValueError
        if type(value["display_zone"]) is not str or len(value["display_zone"]) > 64:
            raise ValueError
        ZoneInfo(value["display_zone"])
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise JournalError("Invalid display time or zone") from error
    groups, bases = value["groups"], value["bases"]
    if (type(groups) is not dict or type(bases) is not dict or len(groups) > 16
            or set(groups) != set(bases) or any(not GROUP.fullmatch(k) for k in groups)):
        raise JournalError("Invalid field groups")
    if not value["kind"].endswith(".delete") and not groups:
        raise JournalError("An addition or edit needs field groups")
    for base in bases.values():
        if base is not None:
            hash_value(base)
    if value["kind"].endswith(".add") and any(base is not None for base in bases.values()):
        raise JournalError("An addition cannot have existing base tokens")
    dependencies = value["dependencies"]
    if type(dependencies) is not list or len(dependencies) > 32:
        raise JournalError("Invalid dependencies")
    ids = []
    for dependency in dependencies:
        origin(dependency)
        if (dependency["device"] != value["origin"]["device"]
                or dependency["incarnation"] != value["origin"]["incarnation"]
                or dependency["seq"] >= value["origin"]["seq"]):
            raise JournalError("Laboratory dependencies must be earlier edits from this origin")
        ids.append(origin_id(dependency))
    if len(ids) != len(set(ids)):
        raise JournalError("Duplicate dependency")
    cursor(value["cursor"])


def cursor(value):
    fields(value, ("revision", "hash"))
    number(value["revision"])
    hash_value(value["hash"])
    if value["revision"] == 0 and value["hash"] != ZERO_HASH:
        raise JournalError("Invalid initial cursor")


def seal(body, signer) -> bytes:
    payload = canonical(body)
    wire = canonical({"body": body, "signature": signer(payload)})
    if len(wire) > MAX_MESSAGE:
        raise JournalError("Message size limit exceeded")
    return wire


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JournalError("Duplicate JSON key")
        result[key] = value
    return result


def unpack(wire: bytes):
    if type(wire) is not bytes or len(wire) > MAX_MESSAGE:
        raise JournalError("Message size limit exceeded")
    try:
        value = json.loads(wire, object_pairs_hook=_pairs)
        _tree(value)
        fields(value, ("body", "signature"))
        if (type(value["signature"]) is not str or
                re.fullmatch(r"[0-9a-f]{16,160}", value["signature"]) is None):
            raise JournalError("Invalid signature encoding")
        if canonical(value) != wire:
            raise JournalError("Noncanonical encoding")
        return value
    except (ValueError, UnicodeError, RecursionError, TypeError) as error:
        raise JournalError("Invalid message encoding") from error


def authenticate(envelope, public_key):
    if not verify_signature(public_key, canonical(envelope["body"]), envelope["signature"]):
        raise JournalError("Invalid signature")
