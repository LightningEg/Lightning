"""OS-bound protection for transport identities, independent of profile passwords.

Windows binds ciphertext to the current user through DPAPI. Android wraps with
an app-owned, non-exportable Keystore AES key. Linux is a development/test host;
it keeps the existing private-file format. Native-provider errors never select
that development fallback.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from typing import Protocol

_android_bridge = None  # Installed by the Android-only Python adapter before identity use.


class DeviceCredentialError(ValueError):
    """Preserve the identity and reconnect explicitly if its OS binding is lost."""


class Protector(Protocol):
    name: str

    def protect(self, data: bytes, aad: bytes) -> bytes: ...

    def unprotect(self, data: bytes, aad: bytes) -> bytes: ...


class WindowsProtector:
    name = "windows-dpapi-v1"

    @staticmethod
    def _crypt(data: bytes, aad: bytes, *, decrypt: bool) -> bytes:
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

        source = ctypes.create_string_buffer(data)
        entropy = ctypes.create_string_buffer(aad)
        incoming = Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
        binding = Blob(len(aad), ctypes.cast(entropy, ctypes.POINTER(ctypes.c_ubyte)))
        output = Blob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        function.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        # CRYPTPROTECT_UI_FORBIDDEN; never use LOCAL_MACHINE or interactive prompts.
        if not function(ctypes.byref(incoming), None, ctypes.byref(binding), None, None, 1, ctypes.byref(output)):
            raise DeviceCredentialError("Windows could not open this device identity. Use its original Windows account or pair again.")
        try:
            return ctypes.string_at(output.data, output.size)
        finally:
            if output.data:
                ctypes.memset(output.data, 0, output.size)
                kernel32.LocalFree(output.data)

    def protect(self, data: bytes, aad: bytes) -> bytes:
        return self._crypt(data, aad, decrypt=False)

    def unprotect(self, data: bytes, aad: bytes) -> bytes:
        return self._crypt(data, aad, decrypt=True)


class AndroidProtector:
    name = "android-keystore-v1"

    def __init__(self, bridge=None):
        if bridge is None:
            bridge = _android_bridge
        if bridge is None:
            raise DeviceCredentialError("Android Keystore is unavailable. This device identity was preserved.")
        self.bridge = bridge

    def _call(self, method, data, aad):
        try:
            reply = json.loads(str(getattr(self.bridge, method)(
                base64.b64encode(data).decode("ascii"), base64.b64encode(aad).decode("ascii"))))
            if set(reply) != {"data"}:
                raise ValueError("Keystore refused")
            value = base64.b64decode(reply["data"], validate=True)
            if not 0 < len(value) <= 32768:
                raise ValueError("Invalid Keystore reply")
            return value
        except Exception as error:
            raise DeviceCredentialError("Android could not open this device identity. Pair again if its Keystore key was lost.") from error

    def protect(self, data, aad):
        return self._call("protect", data, aad)

    def unprotect(self, data, aad):
        return self._call("unprotect", data, aad)


def configure_android_credentials(bridge) -> None:
    """Inject the app's Java bridge from Android code, which is not shipped on PC."""
    global _android_bridge
    if not callable(getattr(bridge, "protect", None)) or not callable(getattr(bridge, "unprotect", None)):
        raise DeviceCredentialError("Android device credential adapter is unavailable")
    _android_bridge = bridge


def native_protector() -> Protector | None:
    if _android_bridge is not None:
        return AndroidProtector(_android_bridge)
    if sys.platform == "win32":
        return WindowsProtector()
    if sys.platform == "android" or hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ:
        return AndroidProtector()
    return None


def seal(data: bytes, aad: bytes, protector: Protector) -> bytes:
    payload = protector.protect(data, aad)
    if not 0 < len(payload) <= 32768:
        raise DeviceCredentialError("Invalid protected device identity")
    return json.dumps(dict(format=1, provider=protector.name,
                           sealed=base64.b64encode(payload).decode("ascii")), separators=(",", ":")).encode("ascii")


def unseal(data: bytes, aad: bytes, protector: Protector | None) -> bytes:
    try:
        record = json.loads(data)
        if (set(record) != {"format", "provider", "sealed"} or type(record["format"]) is not int
                or record["format"] != 1 or protector is None or record["provider"] != protector.name):
            raise ValueError("Identity protection does not match this device")
        payload = base64.b64decode(record["sealed"], validate=True)
        if not 0 < len(payload) <= 32768:
            raise ValueError("Invalid protected device identity")
        result = protector.unprotect(payload, aad)
        if not 0 < len(result) <= 16384:
            raise ValueError("Invalid private key")
        return result
    except DeviceCredentialError:
        raise
    except Exception as error:
        raise DeviceCredentialError("This device identity is damaged or belongs to another OS account. Preserve it and pair again.") from error
