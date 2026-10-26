"""Dummy-only native credential probe; no finance profile is opened or modified."""
from __future__ import annotations

import argparse
import json
import ssl
import tempfile
from pathlib import Path

from lightning.security.device_credentials import DeviceCredentialError, native_protector
from lightning.sync.identity import load_or_create, verify_signature


def credential_checks(*, require_native=False):
    protector = native_protector()
    if require_native and protector is None:
        raise DeviceCredentialError("A native Windows or Android credential provider is required")
    checks = {}
    with tempfile.TemporaryDirectory(prefix="lightning-credential-probe-") as folder:
        root = Path(folder)
        first = load_or_create(root / "identity", "Dummy device", protector=protector)
        public, fingerprint, identifier = first.public_key, first.fingerprint, first.device_id
        signature = first.sign(b"dummy native credential check")
        restarted = load_or_create(root / "identity", "Dummy device", protector=protector)
        checks["identity_survives_reload"] = (restarted.device_id == identifier and restarted.fingerprint == fingerprint
            and verify_signature(public, b"dummy native credential check", signature))
        stored = first.key_path.read_bytes()
        checks["os_protected_storage"] = protector is not None and b"PRIVATE KEY" not in stored
        if protector is None:
            # This is an explicitly labelled development host, not native evidence.
            checks.pop("os_protected_storage")
        with first.tls_files() as (cert, key, password):
            checks["encrypted_tls_temporary_file"] = b"BEGIN ENCRYPTED PRIVATE KEY" in Path(key).read_bytes()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key, password)
        checks["tls_temporary_file_removed"] = not Path(key).exists()
        first.load_cert_chain(context)
        checks["tls_13_minimum"] = context.minimum_version == ssl.TLSVersion.TLSv1_3
        if protector is not None:
            binding = b"dummy credential binding A"
            wrapped = protector.protect(b"dummy credential", binding)
            checks["native_round_trip"] = protector.unprotect(wrapped, binding) == b"dummy credential"
            try:
                protector.unprotect(wrapped, b"dummy credential binding B")
            except DeviceCredentialError:
                checks["native_wrong_binding_rejected"] = True
            else:
                checks["native_wrong_binding_rejected"] = False
            try:
                protector.unprotect(wrapped[:-1] + bytes([wrapped[-1] ^ 1]), binding)
            except DeviceCredentialError:
                checks["native_tamper_rejected"] = True
            else:
                checks["native_tamper_rejected"] = False
        checks["certificate_and_public_key_preserved"] = (restarted.public_key == public and restarted.fingerprint == fingerprint)
    return dict(format=1, dummy_only=True, provider=protector.name if protector else "linux-development-private-file",
                native_provider=protector is not None, passed=all(checks.values()), checks=checks,
                physical_wifi="not_run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    try:
        report = credential_checks(require_native=args.require_native)
    except (DeviceCredentialError, OSError, ValueError):
        # Do not print exception chains, paths or any private credential material.
        report = dict(format=1, dummy_only=True, passed=False, error="credential_probe_failed")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
