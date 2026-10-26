"""Verify store entitlement signatures offline. No private keys, device binding or expiry.

This module grants cosmetic IDs only. It cannot affect ledger balances, calculations or roles.
The caller supplies the built-in supported registry and pinned public keys, never downloaded keys.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class InvalidCosmeticLicense(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidCosmeticLicense("Duplicate license field")
        result[key] = value
    return result


@dataclass(frozen=True)
class CosmeticOwnership:
    account_id: str
    items: tuple[tuple[str, int], ...]


def verify_license(envelope: dict, public_keys: dict[str, bytes], supported: dict[str, int],
                   *, expected_account: str | None = None) -> CosmeticOwnership:
    """Verify first, parse second; fail closed on unshipped items and account mismatch.

    Public keys are raw 32-byte Ed25519 keys pinned in an app release. Key rotation must
    retain old verification keys for permanent offline licenses. Empty keys unlock nothing.
    """
    try:
        if envelope.get("algorithm") != "Ed25519":
            raise InvalidCosmeticLicense("Unsupported signature algorithm")
        key = public_keys.get(envelope.get("key_id"))
        payload, signature = envelope.get("payload"), envelope.get("signature")
        if not key or not isinstance(payload, str) or len(payload.encode("utf-8")) > 131072:
            raise InvalidCosmeticLicense("Unknown signing key or invalid payload")
        if not isinstance(signature, str) or not re.fullmatch(r"[A-Za-z0-9_-]{86}", signature):
            raise InvalidCosmeticLicense("Invalid signature encoding")
        raw = base64.b64decode(signature + "==", altchars=b"-_", validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(raw, payload.encode("utf-8"))
        data = json.loads(payload, object_pairs_hook=_object)
        if data.get("issuer") != "lightning-store" or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise InvalidCosmeticLicense("Unsupported license")
        account = str(UUID(data["account_id"]))
        if expected_account is not None and account != expected_account:
            raise InvalidCosmeticLicense("License belongs to a different store account")
        items = data["items"]
        if not isinstance(items, list) or len(items) > 500:
            raise InvalidCosmeticLicense("Invalid item list")
        owned = []
        for item in items:
            name, version = item["item_id"], item["asset_version"]
            if not isinstance(name, str) or type(version) is not int or supported.get(name) != version:
                raise InvalidCosmeticLicense("Update Lightning: unsupported bundled item version")
            if any(name == existing[0] for existing in owned):
                raise InvalidCosmeticLicense("Duplicate item")
            owned.append((name, version))
        return CosmeticOwnership(account, tuple(owned))
    except (InvalidSignature, ValueError, TypeError, KeyError, AttributeError) as exc:
        if isinstance(exc, InvalidCosmeticLicense):
            raise
        raise InvalidCosmeticLicense("Invalid cosmetic license") from exc
