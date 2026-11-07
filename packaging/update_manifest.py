"""Sign and verify a release's update manifest (NF-9B1).

  python packaging/update_manifest.py sign   --dir release --tag v2.0.4 --zip <ZIP name>   (key in $UPDATE_SIGNING_KEY)
  python packaging/update_manifest.py verify --dir release --tag v2.0.4 [--zip <ZIP name>]

`sign` writes UPDATE.json and UPDATE.json.sig beside the ZIP. The signature is Ed25519 over LABEL + the exact bytes of
UPDATE.json, so a theme licence signed by the same store key can never pass as an update. The private key is the whole
JWK (`d`, `x`, `kid`, as tools/store_keygen.py makes it) in the environment, never on disk or in the output.
`verify` checks the pair against lightning/security/update_keys.json: the app does the same in 9B2.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "lightning" / "security" / "update_keys.json"
LABEL = b"lightning-update-v1:"
MANIFEST, SIGNATURE = "UPDATE.json", "UPDATE.json.sig"
FIELDS = ("format", "version", "zip", "sha256", "size", "released", "key_id")


class ManifestError(ValueError):
    """A reason a manifest or signature cannot be trusted."""


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def load_keys(path: Path = KEYS) -> dict[str, bytes]:
    return {kid: _unb64(raw) for kid, raw in json.loads(path.read_text(encoding="utf-8")).get("keys", {}).items()}


def verify(manifest: bytes, signature_b64: str | bytes, keys: dict[str, bytes], *, tag: str | None = None) -> dict:
    """The parsed manifest if its signature is good and (given a tag) it is that release; else ManifestError."""
    try:
        data = json.loads(manifest)
    except ValueError as error:
        raise ManifestError("UPDATE.json is not JSON") from error
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise ManifestError("UPDATE.json does not have exactly the expected fields")
    key = keys.get(data["key_id"]) if isinstance(data["key_id"], str) else None
    if key is None:
        raise ManifestError(f"unknown update key {data['key_id']!r}")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(base64.b64decode(signature_b64, validate=True), LABEL + manifest)
    except (InvalidSignature, ValueError) as error:
        raise ManifestError("the update signature does not match") from error
    if data["format"] != 1:
        raise ManifestError(f"unsupported manifest format {data['format']!r}")
    version, name, sha, size = data["version"], data["zip"], data["sha256"], data["size"]
    if not (isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version)):
        raise ManifestError("the manifest version is not a plain release version")
    if name != f"Lightning-v{version}-Windows-x64.zip":
        raise ManifestError("the manifest's ZIP name does not match its version")
    if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
        raise ManifestError("the manifest's sha256 is malformed")
    if not (isinstance(size, int) and not isinstance(size, bool) and size > 0):
        raise ManifestError("the manifest's size is malformed")
    if tag is not None and tag != f"v{version}":
        raise ManifestError(f"the manifest is for {version}, not {tag}")
    return data


def _source_version() -> str:
    match = re.search(r'^DISPLAY_VERSION = "([^"]+)"', (ROOT / "lightning" / "__init__.py").read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else ""


def sign(directory: Path, tag: str, zip_name: str, jwk_text: str, *, keys: dict[str, bytes] | None = None,
         source_version: str | None = None, today: str | None = None) -> dict:
    keys = load_keys() if keys is None else keys
    if not jwk_text.strip():
        raise ManifestError("UPDATE_SIGNING_KEY is not set: nothing was signed")
    try:
        jwk = json.loads(jwk_text)
        private = Ed25519PrivateKey.from_private_bytes(_unb64(jwk["d"]))
        key_id = jwk["kid"]
    except (ValueError, KeyError, TypeError) as error:
        raise ManifestError("UPDATE_SIGNING_KEY is not an Ed25519 private JWK with d and kid") from error
    from cryptography.hazmat.primitives import serialization
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if keys.get(key_id) != public:
        raise ManifestError(f"the signing key {key_id!r} is not pinned in update_keys.json: the app would refuse it")
    version = tag[1:] if tag.startswith("v") else tag
    if version != (source_version if source_version is not None else _source_version()):
        raise ManifestError(f"tag {tag} is not the source version")
    zip_path = directory / zip_name
    if not zip_path.is_file():
        raise ManifestError(f"{zip_name} is not in {directory}")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sums = (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    if f"{digest}  {zip_name}" not in sums:
        raise ManifestError(f"SHA256SUMS does not hold {zip_name}'s hash")
    manifest = {"format": 1, "version": version, "zip": zip_name, "sha256": digest, "size": zip_path.stat().st_size,
                "released": today or datetime.now(timezone.utc).strftime("%Y-%m-%d"), "key_id": key_id}
    raw = (json.dumps(manifest, indent=2) + "\n").encode()
    signature = base64.b64encode(private.sign(LABEL + raw))
    verify(raw, signature, keys, tag=tag)  # never write a pair the app would refuse
    (directory / MANIFEST).write_bytes(raw)
    (directory / SIGNATURE).write_bytes(signature + b"\n")
    return manifest


def check_files(directory: Path, tag: str, zip_name: str | None = None, keys: dict[str, bytes] | None = None) -> dict:
    """verify() for the two files in a folder, plus the ZIP itself when it is named."""
    try:
        raw = (directory / MANIFEST).read_bytes()
        signature = (directory / SIGNATURE).read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise ManifestError(f"{MANIFEST} or {SIGNATURE} is missing or unreadable") from error
    data = verify(raw, signature, load_keys() if keys is None else keys, tag=tag)
    if zip_name is not None:
        path = directory / zip_name
        if data["zip"] != zip_name or not path.is_file():
            raise ManifestError("the manifest does not describe this ZIP")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != data["sha256"] or len(body) != data["size"]:
            raise ManifestError("the ZIP differs from its signed manifest")
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("sign", "verify"))
    parser.add_argument("--dir", type=Path, default=Path("."))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--zip")
    parser.add_argument("--keys", type=Path, help="pinned public keys (tests only; default update_keys.json)")
    args = parser.parse_args(argv)
    try:
        if args.command == "sign":
            if not args.zip:
                parser.error("sign needs --zip")
            data = sign(args.dir, args.tag, args.zip, os.environ.get("UPDATE_SIGNING_KEY", ""),
                        keys=load_keys(args.keys) if args.keys else None)
            print(f"Signed {MANIFEST} for {data['version']} with {data['key_id']}.")
        else:
            data = check_files(args.dir, args.tag, args.zip, load_keys(args.keys) if args.keys else None)
            print(f"{MANIFEST} is signed by {data['key_id']} for {data['version']}.")
    except ManifestError as error:
        print(f"::error::{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
