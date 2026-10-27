"""Make the Lightning store's Ed25519 signing key (8L step 3). Run once, on the owner's own computer.

Writes the PRIVATE JWK to the file you name (never printed, never in Git) and prints the PUBLIC half.
  1. Back the private file up offline, then set the Supabase secrets:
       STORE_SIGNING_PRIVATE_JWK = the file's whole content    STORE_SIGNING_KEY_ID = the id printed below
  2. Give an AI only the printed public key and id: it goes in lightning/security/store_keys.json.
Licences are permanent and offline: losing this key means every licence must be reissued; leaking it lets
anyone forge a theme licence. Cosmetics only, never money.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_key(key_id: str) -> tuple[dict, str]:
    """(private JWK as the store function imports it, raw public key in base64url as store_keys.json holds it)."""
    private = Ed25519PrivateKey.generate()
    seed = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "d": b64url(seed), "x": b64url(public), "kid": key_id}, b64url(public)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("private_file", type=Path, help="where to write the private JWK (must not exist)")
    parser.add_argument("--id", default="store-2026-1", dest="key_id", help="key id, letters digits . _ - (default store-2026-1)")
    args = parser.parse_args(argv)
    jwk, public = make_key(args.key_id)
    try:
        fd = os.open(args.private_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"{args.private_file} exists: refusing to overwrite a key.", file=sys.stderr)
        return 1
    with os.fdopen(fd, "w") as handle:
        json.dump(jwk, handle)
    print(f"Private key written to {args.private_file}. Back it up offline; never commit it.")
    print(f'Public, safe to share:  "{args.key_id}": "{public}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
