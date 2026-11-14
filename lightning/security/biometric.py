"""Optional fingerprint unlock on the phone (task 18d, owner-approved 2026-10-14).

The profile's data key is wrapped a third way, by an Android Keystore key that only a strong biometric can use.
The wrapped copy (`biometric/<profile id>.json`) lives in the phone app's private storage, beside the sync
records and outside the profile folder, so `keys.json` and the PC are untouched. The raw data key is never
written to disk, and a screen callback alone never releases it: Android hands the Keystore key to the cipher
only after the fingerprint (`BiometricPrompt` with a `CryptoObject`, in `BiometricBridge.java`).

This module holds what is testable without a phone: the slot file, the rules for when to offer the option,
and what each outcome means. The Android bridge is `lightning_android.AndroidBiometric`; tests use a fake."""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from .keys import key_id

SLOT_VERSION = 1
_MAX_SLOT_BYTES = 4096
_PROFILE_ID = re.compile(r"[0-9a-f-]{8,36}\Z")
_KEY_ID = re.compile(r"[0-9a-f]{16}\Z")
_IV_BYTES = 12
_CIPHERTEXT_BYTES = 32 + 16  # the data key and the GCM tag


class Outcome(Enum):
    OK = "ok"
    CANCELLED = "cancelled"
    LOCKOUT = "lockout"
    INVALIDATED = "invalidated"
    UNAVAILABLE = "unavailable"
    MISMATCH = "mismatch"  # the key opened, but it is not this profile's key


@dataclass(frozen=True)
class BridgeResult:
    """What the Android side answers: an outcome, and for `ok` the data."""
    outcome: Outcome
    iv: bytes = b""
    data: bytes = b""


class BiometricBridge(Protocol):
    """The phone's side. Calls block until the person answers, so call them off the UI and request threads."""

    def available(self) -> bool:
        """A strong biometric is enrolled on this phone and the API level supports key-bound prompts."""

    def encrypt(self, profile_id: str, plaintext: bytes, aad: bytes) -> BridgeResult:
        """Make the Keystore key if needed, ask for the fingerprint, return iv and ciphertext."""

    def decrypt(self, profile_id: str, iv: bytes, ciphertext: bytes, aad: bytes) -> BridgeResult:
        """Ask for the fingerprint, return the plaintext in `data`."""

    def delete_key(self, profile_id: str) -> None:
        """Remove the Keystore key (it may not exist)."""


@dataclass(frozen=True)
class Unlocked:
    outcome: Outcome
    key: bytes | None = None
    message: str = ""


MESSAGES = {
    Outcome.CANCELLED: "",
    Outcome.LOCKOUT: "Too many fingerprint tries. Unlock with your password, or try the fingerprint later.",
    Outcome.INVALIDATED: "Your phone’s fingerprints changed, so fingerprint unlock was turned off. "
                         "Unlock with your password, then turn fingerprint on again.",
    Outcome.MISMATCH: "Fingerprint unlock no longer matches this profile, so it was turned off. "
                      "Unlock with your password, then turn fingerprint on again.",
    Outcome.UNAVAILABLE: "Fingerprint unlock is not available now. Unlock with your password.",
}
ENROL_MESSAGES = {
    Outcome.CANCELLED: "Fingerprint unlock was not turned on.",
    Outcome.LOCKOUT: "Too many fingerprint tries. Try again later.",
    Outcome.INVALIDATED: "Your phone’s fingerprints changed. Try turning fingerprint on again.",
    Outcome.UNAVAILABLE: "Fingerprint unlock is not available on this phone now.",
    Outcome.MISMATCH: "Fingerprint unlock could not be checked. It was not turned on.",
}


def _aad(profile_id: str, key_ident: str) -> bytes:
    """Bound into the encryption, so a slot moved to another profile or key never opens."""
    return f"lightning/biometric/v1:{profile_id}:{key_ident}".encode("ascii")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(value, length: int) -> bytes:
    if not isinstance(value, str):
        raise ValueError("not text")
    try:
        data = base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ValueError("not base64") from exc
    if len(data) != length:
        raise ValueError("wrong length")
    return data


class SlotStore:
    """One small file per profile under `folder` (the phone's app-data root, `biometric/`)."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)

    def path(self, profile_id: str) -> Path:
        if not isinstance(profile_id, str) or _PROFILE_ID.fullmatch(profile_id) is None:
            raise ValueError("profile_id is not a profile identifier")
        return self.folder / f"{profile_id}.json"

    def read(self, profile_id: str) -> dict | None:
        """The slot, or None when there is none or it is damaged (a damaged one is removed)."""
        path = self.path(profile_id)
        try:
            if path.is_symlink():
                raise ValueError("link")
            with path.open("rb") as handle:
                raw = handle.read(_MAX_SLOT_BYTES + 1)
            if len(raw) > _MAX_SLOT_BYTES:
                raise ValueError("oversized")
            document = json.loads(raw)
            if (not isinstance(document, dict) or document.get("version") != SLOT_VERSION
                    or document.get("profile_id") != profile_id
                    or not isinstance(document.get("key_id"), str) or _KEY_ID.fullmatch(document["key_id"]) is None
                    or not isinstance(document.get("created"), (int, float))):
                raise ValueError("shape")
            _unb64(document.get("iv"), _IV_BYTES)
            _unb64(document.get("ciphertext"), _CIPHERTEXT_BYTES)
            return document
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            self.delete(profile_id)
            return None

    def write(self, profile_id: str, ident: str, iv: bytes, ciphertext: bytes, *, now: float | None = None) -> None:
        path = self.path(profile_id)
        self.folder.mkdir(parents=True, exist_ok=True)
        document = {"version": SLOT_VERSION, "profile_id": profile_id, "key_id": ident, "iv": _b64(iv),
                    "ciphertext": _b64(ciphertext), "created": int(time.time() if now is None else now)}
        temporary = path.with_name(f".bio-{secrets.token_hex(8)}.partial")
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(json.dumps(document, sort_keys=True).encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self, profile_id: str) -> None:
        path = self.path(profile_id)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


class FingerprintUnlock:
    """The slot store and the phone's bridge together. `bridge` is None off the phone: nothing is offered."""

    def __init__(self, folder: str | Path, bridge: BiometricBridge | None):
        self.store = SlotStore(folder)
        self.bridge = bridge

    def available(self) -> bool:
        if self.bridge is None:
            return False
        try:
            return bool(self.bridge.available())
        except Exception:  # noqa: BLE001 - a bridge that fails is not available
            return False

    def enabled(self, profile_id: str) -> bool:
        """A slot exists for this profile (whether or not the phone can use it right now)."""
        return self.store.read(profile_id) is not None

    def offered(self, profile_id: str) -> bool:
        """The unlock screen's "Use fingerprint": a slot exists and the phone can ask for the fingerprint."""
        return self.available() and self.enabled(profile_id)

    def enrol(self, profile_id: str, data_key: bytes) -> Outcome:
        """Wrap `data_key` under the Keystore key. The caller has already proved the password again."""
        if not self.available():
            return Outcome.UNAVAILABLE
        ident = key_id(data_key)
        try:
            result = self.bridge.encrypt(profile_id, data_key, _aad(profile_id, ident))
        except Exception:  # noqa: BLE001
            result = BridgeResult(Outcome.UNAVAILABLE)
        if result.outcome is not Outcome.OK:
            self.bridge_delete(profile_id)  # no half-made key left behind
            self.store.delete(profile_id)
            return result.outcome
        if len(result.iv) != _IV_BYTES or len(result.data) != _CIPHERTEXT_BYTES:
            self.bridge_delete(profile_id)
            return Outcome.UNAVAILABLE
        self.store.write(profile_id, ident, result.iv, result.data)
        return Outcome.OK

    def unlock(self, profile_id: str, expected_key_id: str) -> Unlocked:
        """Ask for the fingerprint and return the data key, but only a key whose `key_id` is `expected_key_id`
        (the one in keys.json). Cancel changes nothing. Anything that says the slot can no longer be trusted
        removes it and the Keystore key."""
        slot = self.store.read(profile_id)
        if slot is None or not self.available():
            return Unlocked(Outcome.UNAVAILABLE, message=MESSAGES[Outcome.UNAVAILABLE])
        if slot["key_id"] != expected_key_id:
            return self._remove(profile_id, Outcome.MISMATCH)
        try:
            result = self.bridge.decrypt(profile_id, _unb64(slot["iv"], _IV_BYTES), _unb64(slot["ciphertext"], _CIPHERTEXT_BYTES),
                                         _aad(profile_id, slot["key_id"]))
        except Exception:  # noqa: BLE001
            result = BridgeResult(Outcome.UNAVAILABLE)
        if result.outcome is Outcome.INVALIDATED:
            return self._remove(profile_id, Outcome.INVALIDATED)
        if result.outcome is not Outcome.OK:
            return Unlocked(result.outcome, message=MESSAGES[result.outcome])
        key = bytes(result.data)
        try:
            right = len(key) == 32 and secrets.compare_digest(key_id(key), expected_key_id)
        except ValueError:
            right = False
        if not right:
            return self._remove(profile_id, Outcome.MISMATCH)
        return Unlocked(Outcome.OK, key)

    def disable(self, profile_id: str) -> None:
        """Delete the slot and the Keystore key. Always both, even when one is already gone."""
        self.store.delete(profile_id)
        self.bridge_delete(profile_id)

    def bridge_delete(self, profile_id: str) -> None:
        if self.bridge is None:
            return
        try:
            self.bridge.delete_key(profile_id)
        except Exception:  # noqa: BLE001 - the slot file is already gone; an orphan Keystore key opens nothing
            pass

    def _remove(self, profile_id: str, outcome: Outcome) -> Unlocked:
        self.disable(profile_id)
        return Unlocked(outcome, message=MESSAGES[outcome])
