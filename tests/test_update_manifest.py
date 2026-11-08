"""The update manifest: signed with a labelled Ed25519 signature, verified against pinned keys (NF-9B1).

Every key here is made inside the test; the real update key never appears.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "packaging"), str(ROOT / "tools")]
import update_manifest as um  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from store_keygen import make_key  # noqa: E402

TAG, ZIP = "v2.0.4", "Lightning-v2.0.4-Windows-x64.zip"


@pytest.fixture
def signed(tmp_path):
    jwk, public = make_key("test-1")
    keys = {"test-1": um._unb64(public)}
    body = b"zip bytes" * 100
    (tmp_path / ZIP).write_bytes(body)
    (tmp_path / "SHA256SUMS").write_text(f"{hashlib.sha256(body).hexdigest()}  {ZIP}\n", encoding="utf-8")
    manifest = um.sign(tmp_path, TAG, ZIP, json.dumps(jwk), keys=keys, source_version="2.0.4", today="2026-11-20")
    return tmp_path, keys, jwk, manifest


def raw(d):
    return (d / um.MANIFEST).read_bytes(), (d / um.SIGNATURE).read_text().strip()


def test_the_pinned_update_keys_are_the_store_key_and_update_2026_2():
    store = json.loads((ROOT / "lightning/security/store_keys.json").read_text())["keys"]["store-2026-1"]
    keys = json.loads((ROOT / "lightning/security/update_keys.json").read_text())["keys"]
    assert set(keys) == {"store-2026-1", "update-2026-2"}
    assert keys["store-2026-1"] == store
    assert keys["update-2026-2"] == "DyQUbKqBrpkbjctx1NKeAMtXNu4KTK1EKmiZQTvTA7M"
    assert keys["update-2026-2"] != store
    assert len(um.load_keys()["update-2026-2"]) == 32


def test_a_good_manifest_verifies_and_says_what_the_zip_is(signed):
    d, keys, _, manifest = signed
    assert manifest == {"format": 1, "version": "2.0.4", "zip": ZIP, "size": (d / ZIP).stat().st_size,
                        "sha256": hashlib.sha256((d / ZIP).read_bytes()).hexdigest(), "released": "2026-11-20",
                        "key_id": "test-1"}
    assert um.check_files(d, TAG, ZIP, keys) == manifest


def test_a_signature_without_the_label_fails(signed):
    d, keys, jwk, _ = signed
    body, _ = raw(d)
    bare = Ed25519PrivateKey.from_private_bytes(um._unb64(jwk["d"])).sign(body)  # how a licence is signed
    with pytest.raises(um.ManifestError, match="signature"):
        um.verify(body, base64.b64encode(bare), keys, tag=TAG)


def test_a_changed_byte_an_unknown_key_or_a_wrong_signature_fails(signed):
    d, keys, _, _ = signed
    body, sig = raw(d)
    with pytest.raises(um.ManifestError, match="signature"):
        um.verify(body.replace(b'"size": ', b'"size":  '), sig, keys, tag=TAG)
    with pytest.raises(um.ManifestError, match="unknown update key"):
        um.verify(body, sig, {"other": b"x" * 32}, tag=TAG)
    other = Ed25519PrivateKey.generate()
    with pytest.raises(um.ManifestError, match="signature"):
        um.verify(body, base64.b64encode(other.sign(um.LABEL + body)), keys, tag=TAG)
    with pytest.raises(um.ManifestError):
        um.verify(body, "not base64!!", keys, tag=TAG)


def test_a_version_not_matching_the_tag_fails(signed):
    d, keys, jwk, _ = signed
    body, sig = raw(d)
    with pytest.raises(um.ManifestError, match="not v2.0.5"):
        um.verify(body, sig, keys, tag="v2.0.5")
    with pytest.raises(um.ManifestError, match="not the source version"):
        um.sign(d, TAG, ZIP, json.dumps(jwk), keys=keys, source_version="2.0.3")


def test_signing_refuses_a_zip_whose_hash_is_not_in_sha256sums_or_a_key_that_is_not_pinned(signed):
    d, keys, jwk, _ = signed
    (d / "SHA256SUMS").write_text(f"{'0' * 64}  {ZIP}\n")
    with pytest.raises(um.ManifestError, match="SHA256SUMS"):
        um.sign(d, TAG, ZIP, json.dumps(jwk), keys=keys, source_version="2.0.4")
    with pytest.raises(um.ManifestError, match="not pinned"):
        um.sign(d, TAG, ZIP, json.dumps(jwk), keys={}, source_version="2.0.4")
    with pytest.raises(um.ManifestError, match="not set"):
        um.sign(d, TAG, ZIP, "", keys=keys, source_version="2.0.4")


def test_a_zip_that_differs_from_its_manifest_fails(signed):
    d, keys, _, _ = signed
    (d / ZIP).write_bytes(b"other")
    with pytest.raises(um.ManifestError, match="differs"):
        um.check_files(d, TAG, ZIP, keys)


def test_the_command_line_signs_from_the_environment_and_verifies(signed, monkeypatch, tmp_path, capsys):
    d, keys, jwk, _ = signed
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({"keys": {"test-1": base64.urlsafe_b64encode(keys["test-1"]).decode().rstrip("=")}}))
    monkeypatch.setattr(um, "_source_version", lambda: "2.0.4")
    monkeypatch.setenv("UPDATE_SIGNING_KEY", json.dumps(jwk))
    assert um.main(["sign", "--dir", str(d), "--tag", TAG, "--zip", ZIP, "--keys", str(pins)]) == 0
    assert um.main(["verify", "--dir", str(d), "--tag", TAG, "--zip", ZIP, "--keys", str(pins)]) == 0
    monkeypatch.delenv("UPDATE_SIGNING_KEY")
    assert um.main(["sign", "--dir", str(d), "--tag", TAG, "--zip", ZIP, "--keys", str(pins)]) == 1
    assert json.dumps(jwk["d"]) not in capsys.readouterr().out
