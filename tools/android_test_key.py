"""Make the Android test key that signs every Lightning Test APK (owner, once).

    python android_test_key.py                  # writes to Documents/Lightning test key
    python android_test_key.py <empty folder>

Needs Python 3 and the `cryptography` package (`pip install cryptography`); nothing else. The key never
leaves this PC except as the GitHub environment secrets you paste. The script writes three files into a new
folder and prints what to do with them:

- ANDROID_TEST_KEYSTORE.txt           the key and its certificate (PKCS#12, base64): a secret
- ANDROID_TEST_KEYSTORE_PASSWORD.txt  its password: a secret
- certificate-sha256.txt              the certificate's fingerprint: public, committed as
                                      packaging/android-test-certificate.sha256

Keep the folder (a USB stick or a password manager is fine). If the key is lost, the next APK cannot update
the installed Lightning Test: it must be uninstalled once, losing its dummy data. This key is only for test
builds; it is never a Google Play upload or app signing key. See docs/ARCHITECTURE.md › Build and release.
"""
from __future__ import annotations

import base64
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import PrivateFormat, pkcs12
from cryptography.x509.oid import NameOID

ALIAS = "lightning-test"
YEARS = 30
FILES = ("ANDROID_TEST_KEYSTORE.txt", "ANDROID_TEST_KEYSTORE_PASSWORD.txt", "certificate-sha256.txt")


def make_keystore(password: str, now: datetime | None = None, rounds: int = 600_000) -> tuple[bytes, str]:
    """A PKCS#12 store holding one RSA 3072 key and its self-signed certificate; and the certificate's
    SHA-256 fingerprint as apksigner prints it (64 lowercase hex digits)."""
    now = now or datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Lightning Test (not for release)"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Lightning")])
    certificate = (x509.CertificateBuilder()
                   .subject_name(name).issuer_name(name).public_key(key.public_key())
                   .serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(days=1))
                   .not_valid_after(now + timedelta(days=365 * YEARS))
                   .sign(key, hashes.SHA256()))
    # PBES2 with AES-256 and an SHA-256 MAC: what JDK 17's keytool and apksigner read.
    encryption = (PrivateFormat.PKCS12.encryption_builder()
                  .kdf_rounds(rounds)
                  .key_cert_algorithm(pkcs12.PBES.PBESv2SHA256AndAES256CBC)
                  .hmac_hash(hashes.SHA256())
                  .build(password.encode()))
    store = pkcs12.serialize_key_and_certificates(ALIAS.encode(), key, certificate, None, encryption)
    return store, certificate.fingerprint(hashes.SHA256()).hex()


def write(folder: Path) -> str:
    """Write the three files into a new or empty folder; never overwrite a key."""
    if folder.exists() and any(folder.iterdir()):
        raise SystemExit(f"{folder} is not empty. A test key may already be there: keep it, or choose another folder.")
    folder.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(32)
    store, fingerprint = make_keystore(password)
    contents = (base64.b64encode(store).decode() + "\n", password + "\n", fingerprint + "\n")
    for name, text in zip(FILES, contents, strict=True):
        (folder / name).write_text(text, encoding="ascii")
    return fingerprint


def main(argv: list[str]) -> int:
    folder = Path(argv[0]) if argv else Path.home() / "Documents" / "Lightning test key"
    fingerprint = write(folder)
    print(f"""Made the Lightning Test key in: {folder}

1. On GitHub, open LightningEg/Lightning: Settings > Environments > android-signing.
   Add ANDROID_KEYSTORE_BASE64: everything in ANDROID_TEST_KEYSTORE.txt.
   Add ANDROID_KEYSTORE_PASSWORD: everything in ANDROID_TEST_KEYSTORE_PASSWORD.txt.
   Add ANDROID_KEY_ALIAS: {ALIAS}.
   Add ANDROID_KEY_PASSWORD: the same password from ANDROID_TEST_KEYSTORE_PASSWORD.txt.
2. Send this fingerprint to Claude or Codex to commit (it is public, not a secret):
   {fingerprint}
3. Keep the folder safe. Never put it in the repository or send the two secret files to anyone.""")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
