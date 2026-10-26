"""This device's identity for pairing (multiple devices, task 09).

One ECDSA P-256 key per device: it signs the TLS certificate the phone serves and the challenges a PC
answers. Windows DPAPI and Android Keystore protect the stored key on native devices.
Linux development hosts retain the private-file format. This is independent of
the profile's password-wrapped data key.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import socket
import ssl
import stat
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from lightning.security.device_credentials import DeviceCredentialError, Protector, native_protector, seal, unseal

from .domain import _name

PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0 or 1 to misread
PAIRING_CODE_LENGTH = 12                                 # 60 bits, typed as three groups of four
DEFAULT_PORT = 47513


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    name: str
    key_path: Path
    cert_path: Path
    _protector: Protector | None = field(default=None, repr=False, compare=False)

    def _binding(self) -> bytes:
        return b"lightning-device-identity-v1\0" + self.device_id.encode("ascii") + b"\0" + bytes.fromhex(self.fingerprint)

    def _key(self) -> ec.EllipticCurvePrivateKey:
        try:
            data = _read_identity_file(self.key_path, 65536)
            if data.lstrip().startswith(b"{"):
                data = unseal(data, self._binding(), self._protector or native_protector())
            key = serialization.load_pem_private_key(data, password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
                raise ValueError("Invalid device key")
            certificate = self._certificate()
            if key.public_key().public_numbers() != certificate.public_key().public_numbers():
                raise ValueError("Certificate does not match device key")
            return key
        except DeviceCredentialError:
            raise
        except (OSError, ValueError, TypeError, AttributeError) as error:
            raise DeviceCredentialError("This device identity is missing or damaged. Preserve it and pair again.") from error

    def protect_at_rest(self) -> None:
        """Verify and atomically migrate an existing PEM without replacing its identity."""
        key = self._key()
        protector = self._protector or native_protector()
        if protector is None or self.key_path.read_bytes().lstrip().startswith(b"{"):
            return
        plaintext = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption())
        wrapped = seal(plaintext, self._binding(), protector)
        if not hmac.compare_digest(unseal(wrapped, self._binding(), protector), plaintext):
            raise DeviceCredentialError("Device identity protection could not be verified")
        _replace_private(self.key_path, wrapped)

    def export_private_key(self) -> str:
        """For insertion directly into an already encrypted journal backup only."""
        return self._key().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()).decode("ascii")

    @contextmanager
    def tls_files(self):
        """OpenSSL requires a file; it receives only randomly password-encrypted PEM.

        The password lives in memory and is discarded after SSLContext loading.
        Even an interrupted cleanup leaves no plaintext transport private key.
        """
        password = secrets.token_urlsafe(48)
        encrypted = self._key().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.BestAvailableEncryption(password.encode("ascii")))
        with tempfile.TemporaryDirectory(prefix="lightning-tls-") as folder:
            private = Path(folder) / "encrypted-key.pem"
            _write_private(private, encrypted)
            yield str(self.cert_path), str(private), password

    def load_cert_chain(self, context: ssl.SSLContext) -> None:
        with self.tls_files() as (certificate, private, password):
            context.load_cert_chain(certificate, private, password=password)
        context.minimum_version = ssl.TLSVersion.TLSv1_3

    def configure_uvicorn_tls(self, config):
        """Load TLS eagerly while encrypted temporary material still exists."""
        try:
            with self.tls_files() as (certificate, private, password):
                config.ssl_certfile, config.ssl_keyfile, config.ssl_keyfile_password = certificate, private, password
                config.load()
                config.ssl.minimum_version = ssl.TLSVersion.TLSv1_3
            return config
        finally:
            config.ssl_keyfile_password = None

    @property
    def certificate_der(self) -> bytes:
        return self._certificate().public_bytes(serialization.Encoding.DER)

    def _certificate(self):
        try:
            return x509.load_pem_x509_certificate(_read_identity_file(self.cert_path, 16384))
        except (ValueError, OSError) as error:
            raise DeviceCredentialError("This device certificate is missing or damaged. Preserve it and reconnect explicitly.") from error

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.certificate_der).hexdigest()

    @property
    def public_key(self) -> str:
        """The public key as a compressed point in hex, given to the home at pairing."""
        return self._key().public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint).hex()

    def sign(self, data: bytes) -> str:
        return self._key().sign(data, ec.ECDSA(hashes.SHA256())).hex()


def verify_signature(public_key: str, data: bytes, signature_hex: str) -> bool:
    try:
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(public_key))
        key.verify(bytes.fromhex(signature_hex), data, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _write_private(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _sync_directory(path.parent)


def _read_identity_file(path: Path, maximum: int) -> bytes:
    if path.is_symlink():
        raise DeviceCredentialError("Symbolic device identity files are not accepted")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(descriptor, "rb") as handle:
        details = os.fstat(handle.fileno())
        if not stat.S_ISREG(details.st_mode) or not 0 < details.st_size <= maximum:
            raise DeviceCredentialError("Device identity file has an invalid size or type")
        data = handle.read(maximum + 1)
        if len(data) > maximum:
            raise DeviceCredentialError("Device identity file exceeds its limit")
        return data


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        directory = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _replace_private(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".device-key-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_or_create(folder: str | Path, name: str, *, protector: Protector | None = None) -> DeviceIdentity:
    """This device's identity, created once. The name is what the other device shows ("Office PC")."""
    _name(name, "device name")
    folder = Path(folder)
    if folder.is_symlink():
        raise DeviceCredentialError("Device identity folder must not be a symbolic link")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    meta, key_path, cert_path = folder / "device.json", folder / "device-key.pem", folder / "device-cert.pem"
    protector = protector or native_protector()
    if meta.is_symlink():
        raise DeviceCredentialError("Symbolic device identity metadata is not accepted")
    if meta.exists():
        try:
            record = json.loads(_read_identity_file(meta, 4096))
            uuid.UUID(record["device_id"])
            _name(record["name"], "device name")
        except (ValueError, KeyError, TypeError) as error:
            raise DeviceCredentialError("Device identity metadata is damaged") from error
        identity = DeviceIdentity(record["device_id"], record["name"], key_path, cert_path, protector)
        identity.protect_at_rest()
        if record["name"] != name:
            _replace_private(meta, json.dumps({"device_id": identity.device_id, "name": name}).encode("utf-8"))
            identity = DeviceIdentity(identity.device_id, name, key_path, cert_path, protector)
        return identity
    if key_path.exists() or cert_path.exists() or key_path.is_symlink() or cert_path.is_symlink():
        raise DeviceCredentialError("An interrupted device identity needs explicit repair; its files were preserved")
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Lightning device")])
    now = dt.datetime.now(dt.timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365 * 30))
                   .sign(key, hashes.SHA256()))
    _write_private(cert_path, certificate.public_bytes(serialization.Encoding.PEM))
    device_id = str(uuid.uuid4())
    identity = DeviceIdentity(device_id, name, key_path, cert_path, protector)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    if protector is not None:
        wrapped = seal(private, identity._binding(), protector)
        if not hmac.compare_digest(unseal(wrapped, identity._binding(), protector), private):
            raise DeviceCredentialError("Device identity protection could not be verified")
        private = wrapped
    _write_private(key_path, private)
    _write_private(meta, json.dumps({"device_id": device_id, "name": name}).encode("utf-8"))
    return identity


# ------------------------------------------------------------ pairing secrets and proofs

def new_pairing_code() -> str:
    return "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def normalize_code(text: str) -> str:
    code = "".join(ch for ch in str(text).upper() if not ch.isspace() and ch != "-")
    if len(code) != PAIRING_CODE_LENGTH or any(ch not in PAIRING_ALPHABET for ch in code):
        raise ValueError("Type the 12 letters and digits shown on the phone.")
    return code


def show_code(code: str) -> str:
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def transcript(pairing_id: str, home_fingerprint: str, device_id: str, public_key: str) -> bytes:
    """What both sides bind their proofs to: a relay presenting another certificate cannot match it."""
    return "\n".join(("lightning-pair-v1", pairing_id, home_fingerprint, device_id, public_key)).encode("ascii")


def proof(code: str, role: str, data: bytes) -> str:
    return hmac.new(normalize_code(code).encode("ascii"), role.encode("ascii") + b"\n" + data,
                    hashlib.sha256).hexdigest()


def check_digits(data: bytes) -> str:
    """Six digits both screens show; they match only if both devices saw the same certificate and request."""
    return f"{int.from_bytes(hashlib.sha256(b'digits' + data).digest()[:8], 'big') % 1_000_000:06d}"


def local_address() -> str:
    """This device's address on the local network, for the pairing screen. No packet is sent."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET: only selects the outgoing interface
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()
