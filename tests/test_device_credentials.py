"""Native credential storage preserves identities and never falls back on unwrap failure."""
import json
import os
import ssl
import sys

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from lightning.security.device_credentials import AndroidProtector, DeviceCredentialError, WindowsProtector
from lightning.sync import identity
from test_journal_finance import devices


class TestProtector:
    __test__ = False
    name = "test-aesgcm"

    def __init__(self):
        self.key = AESGCM.generate_key(bit_length=256)

    def protect(self, data, aad):
        nonce = os.urandom(12)
        return nonce + AESGCM(self.key).encrypt(nonce, data, aad)

    def unprotect(self, data, aad):
        return AESGCM(self.key).decrypt(data[:12], data[12:], aad)


def test_protected_identity_survives_restart_without_plaintext_key(tmp_path):
    protector = TestProtector()
    first = identity.load_or_create(tmp_path, "Laptop", protector=protector)
    assert b"PRIVATE KEY" not in first.key_path.read_bytes()
    assert json.loads(first.key_path.read_bytes())["provider"] == protector.name
    signature = first.sign(b"device challenge")
    restarted = identity.load_or_create(tmp_path, "Laptop", protector=protector)
    assert restarted.device_id == first.device_id
    assert restarted.certificate_der == first.certificate_der
    assert identity.verify_signature(restarted.public_key, b"device challenge", signature)


def test_native_migration_keeps_the_same_public_identity_and_verifies_before_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "native_protector", lambda: None)
    original = identity.load_or_create(tmp_path, "Phone")
    public, fingerprint, device = original.public_key, original.fingerprint, original.device_id
    assert b"BEGIN PRIVATE KEY" in original.key_path.read_bytes()
    protected = identity.load_or_create(tmp_path, "Phone", protector=TestProtector())
    assert (protected.public_key, protected.fingerprint, protected.device_id) == (public, fingerprint, device)
    assert b"PRIVATE KEY" not in protected.key_path.read_bytes()


@pytest.mark.parametrize("failure", ["encrypt", "verify", "replace"])
def test_failed_migration_preserves_complete_original(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(identity, "native_protector", lambda: None)
    original = identity.load_or_create(tmp_path, "Phone")
    previous = original.key_path.read_bytes()
    protector = TestProtector()
    def fail(*args, **kwargs):
        raise DeviceCredentialError("injected failure")
    if failure == "encrypt":
        monkeypatch.setattr(protector, "protect", fail)
    elif failure == "verify":
        monkeypatch.setattr(protector, "unprotect", fail)
    else:
        monkeypatch.setattr(identity.os, "replace", fail)
    with pytest.raises(DeviceCredentialError):
        identity.load_or_create(tmp_path, "Phone", protector=protector)
    assert original.key_path.read_bytes() == previous
    assert original.sign(b"still intact")
    assert not list(tmp_path.glob(".device-key-*"))


@pytest.mark.parametrize("damage", ["ciphertext", "provider", "device", "certificate", "missing-key", "missing-meta",
                                     "oversized-key", "oversized-certificate", "oversized-metadata"])
def test_damaged_or_swapped_identity_fails_closed(tmp_path, damage):
    protector = TestProtector()
    current = identity.load_or_create(tmp_path / "one", "Phone", protector=protector)
    if damage in ("ciphertext", "provider"):
        record = json.loads(current.key_path.read_bytes())
        record["provider" if damage == "provider" else "sealed"] = "unknown" if damage == "provider" else "AAAA"
        current.key_path.write_text(json.dumps(record))
    elif damage == "device":
        meta = current.key_path.parent / "device.json"
        record = json.loads(meta.read_bytes())
        record["device_id"] = "00000000-0000-4000-8000-000000000001"
        meta.write_text(json.dumps(record))
    elif damage == "certificate":
        other = identity.load_or_create(tmp_path / "two", "Other", protector=protector)
        current.cert_path.write_bytes(other.cert_path.read_bytes())
    elif damage.startswith("oversized"):
        path = {"oversized-key":current.key_path, "oversized-certificate":current.cert_path,
                "oversized-metadata":current.key_path.parent / "device.json"}[damage]
        path.write_bytes(b"x" * 70000)
    elif damage == "missing-key":
        current.key_path.unlink()
    else:
        (current.key_path.parent / "device.json").unlink()
    before = {path.name: path.read_bytes() for path in current.key_path.parent.iterdir()}
    with pytest.raises(DeviceCredentialError):
        identity.load_or_create(current.key_path.parent, "Phone", protector=protector)
    assert {path.name: path.read_bytes() for path in current.key_path.parent.iterdir()} == before


def test_provider_unavailable_cannot_turn_a_protected_identity_into_plaintext(tmp_path, monkeypatch):
    current = identity.load_or_create(tmp_path, "Phone", protector=TestProtector())
    saved = current.key_path.read_bytes()
    monkeypatch.setattr(identity, "native_protector", lambda: None)
    with pytest.raises(DeviceCredentialError):
        identity.load_or_create(tmp_path, "Phone")
    assert current.key_path.read_bytes() == saved


def test_tls_loads_only_encrypted_ephemeral_files_and_keeps_context_usable(tmp_path):
    current = identity.load_or_create(tmp_path, "Phone", protector=TestProtector())
    with current.tls_files() as (certificate, private, password):
        from pathlib import Path
        private = Path(private)
        assert b"BEGIN ENCRYPTED PRIVATE KEY" in private.read_bytes()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, private, password)
    assert not private.exists()
    current.load_cert_chain(context)
    assert context.minimum_version == ssl.TLSVersion.TLSv1_3


def test_uvicorn_context_is_loaded_before_files_and_password_are_discarded(tmp_path):
    import uvicorn
    current = identity.load_or_create(tmp_path, "Phone", protector=TestProtector())
    async def app(scope, receive, send):
        pass
    config = current.configure_uvicorn_tls(uvicorn.Config(app))
    from pathlib import Path
    assert config.loaded and config.ssl is not None
    assert config.ssl.minimum_version == ssl.TLSVersion.TLSv1_3
    assert config.ssl_keyfile_password is None
    assert not Path(config.ssl_keyfile).exists()


def test_android_bridge_errors_fail_closed():
    class MissingKey:
        def unprotect(self, data, aad):
            return '{"error":"unavailable"}'
    with pytest.raises(DeviceCredentialError):
        AndroidProtector(MissingKey()).unprotect(b"ciphertext", b"binding")


def test_android_adapter_is_injected_and_missing_native_adapter_never_uses_development_fallback(monkeypatch):
    from lightning.security import device_credentials
    monkeypatch.setattr(device_credentials, "_android_bridge", None)
    monkeypatch.setattr(device_credentials.sys, "platform", "android")
    with pytest.raises(DeviceCredentialError):
        device_credentials.native_protector()
    class Adapter:
        @staticmethod
        def protect(data, aad): return '{"error":"unavailable"}'
        @staticmethod
        def unprotect(data, aad): return '{"error":"unavailable"}'
    device_credentials.configure_android_credentials(Adapter)
    assert device_credentials.native_protector().name == "android-keystore-v1"
    with pytest.raises(DeviceCredentialError):
        device_credentials.native_protector().protect(b"dummy", b"binding")


def test_protected_identity_backup_is_portable_only_inside_encrypted_database(devices, tmp_path):
    from dataclasses import replace
    from lightning.database.connection import Database
    from test_journal_backups import backup
    device = devices[1]
    # Native fixtures are already DPAPI-wrapped; preserve their original OS
    # provider. Development fixtures are raw PEM and use an injected protector.
    device.identity = replace(device.identity, _protector=device.identity._protector or TestProtector())
    device.identity.protect_at_rest()
    source = tmp_path / "encrypted-credential-backup.db"
    backup(device, source)
    assert b"PRIVATE KEY" not in source.read_bytes()
    saved = Database(source, key=device.c.db.copy_key(), read_only=True)
    try:
        material = json.loads(saved.scalar("SELECT document FROM journal_backup_material WHERE id=1"))
        assert material["private_key"].startswith("-----BEGIN " + "PRIVATE KEY-----")
        assert material["private_key"] == device.identity.export_private_key()
    finally:
        saved.close()


def test_development_probe_does_not_claim_native_or_physical_evidence(monkeypatch):
    from lightning.runtime import pairing_probe
    monkeypatch.setattr(pairing_probe, "native_protector", lambda: None)
    monkeypatch.setattr(identity, "native_protector", lambda: None)
    report = pairing_probe.credential_checks()
    assert report["passed"] and report["dummy_only"]
    assert not report["native_provider"]
    assert report["physical_wifi"] == "not_run"
    with pytest.raises(DeviceCredentialError):
        pairing_probe.credential_checks(require_native=True)


@pytest.mark.skipif(sys.platform != "win32", reason="requires actual Windows DPAPI")
def test_real_windows_dpapi_is_bound_to_identity_and_rejects_tamper(tmp_path):
    protector = WindowsProtector()
    value = protector.protect(b"dummy credential", b"identity A")
    assert value != b"dummy credential"
    assert protector.unprotect(value, b"identity A") == b"dummy credential"
    with pytest.raises(DeviceCredentialError):
        protector.unprotect(value, b"identity B")
    with pytest.raises(DeviceCredentialError):
        protector.unprotect(value[:-1] + bytes([value[-1] ^ 1]), b"identity A")
    key = identity.load_or_create(tmp_path, "Windows test")
    assert json.loads(key.key_path.read_bytes())["provider"] == "windows-dpapi-v1"
    key.load_cert_chain(ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER))
