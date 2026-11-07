"""NF-9B2: check, download and stage a signed update, with a fake network and a tiny signed fake ZIP.

Keys are made inside the test; nothing touches the network or the real update key.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "packaging"), str(ROOT / "tools")]
import update_manifest as um  # noqa: E402
from store_keygen import make_key  # noqa: E402

from lightning.desktop import update as up  # noqa: E402

VERSION = "2.0.4"
ZIP = f"Lightning-v{VERSION}-Windows-x64.zip"
BASE = "https://example.test/dl/"


def make_zip(files: dict[str, bytes] | None = None, *, prefix="Lightning/") -> bytes:
    files = files if files is not None else {"Lightning.exe": b"exe", "BUILD_INFO.txt": f"Lightning {VERSION} for Windows x64\n".encode(),
                                             "lib/a.dll": b"dll"}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in files.items():
            archive.writestr(prefix + name, body)
    return buffer.getvalue()


class World:
    """A fake release: the ZIP, its signed manifest and a `get` that serves them."""

    def __init__(self, tmp_path, *, zip_bytes=None, version=VERSION, tamper=None):
        self.jwk, public = make_key("test-1")
        self.keys = {"test-1": um._unb64(public)}
        self.zip = zip_bytes if zip_bytes is not None else make_zip()
        folder = tmp_path / "release"
        folder.mkdir()
        (folder / ZIP).write_bytes(self.zip)
        (folder / "SHA256SUMS").write_text(f"{hashlib.sha256(self.zip).hexdigest()}  {ZIP}\n")
        um.sign(folder, f"v{VERSION}", ZIP, json.dumps(self.jwk), keys=self.keys, source_version=VERSION, today="2026-11-20")
        manifest = json.loads((folder / um.MANIFEST).read_text())
        if version != VERSION:  # a validly signed manifest for another version
            manifest.update(version=version, zip=f"Lightning-v{version}-Windows-x64.zip")
            raw = (json.dumps(manifest, indent=2) + "\n").encode()
            sig = base64.b64encode(um.Ed25519PrivateKey.from_private_bytes(um._unb64(self.jwk["d"])).sign(um.LABEL + raw))
            (folder / um.MANIFEST).write_bytes(raw)
            (folder / um.SIGNATURE).write_bytes(sig)
        self.manifest_zip = manifest["zip"]
        self.files = {"UPDATE.json": (folder / um.MANIFEST).read_bytes(),
                      "UPDATE.json.sig": (folder / um.SIGNATURE).read_bytes(), self.manifest_zip: self.zip}
        if tamper:
            tamper(self.files)
        names = [n for n in self.files]
        self.release = json.dumps({"assets": [{"name": n, "browser_download_url": BASE + n} for n in names]}).encode()
        self.requests: list[str] = []

    def get(self, url):
        self.requests.append(url)
        if url == up.RELEASES_URL:
            return self.release
        return self.files[url.removeprefix(BASE)]

    def check(self, current="2.0.3"):
        return up.check(get=self.get, current=current, keys=self.keys)

    def stream(self, url):
        data = self.files[url.removeprefix(BASE)]
        for i in range(0, len(data), 40):
            yield data[i:i + 40]


def available(world):
    found = world.check()
    assert isinstance(found, up.Available), found
    return found


def test_a_newer_signed_release_is_available_with_its_size(tmp_path):
    world = World(tmp_path)
    found = available(world)
    assert (found.version, found.size, found.zip_name) == (VERSION, len(world.zip), ZIP)
    assert world.requests[0] == up.RELEASES_URL and found.zip_url == BASE + ZIP


def test_the_same_or_an_older_version_is_up_to_date(tmp_path):
    world = World(tmp_path)
    assert world.check(current=VERSION) == up.UpToDate()
    assert world.check(current="2.1.0") == up.UpToDate()
    (tmp_path / "o").mkdir()
    assert World(tmp_path / "o", version="2.0.2").check() == up.UpToDate()


def test_a_bad_signature_is_refused(tmp_path):
    def flip(files):
        files["UPDATE.json"] = files["UPDATE.json"].replace(b'"size": ', b'"size":  ')
    (tmp_path / "x").mkdir()
    found = World(tmp_path, tamper=flip).check()
    assert isinstance(found, up.Failed) and "signature" in found.reason
    world = World(tmp_path / "x")
    assert isinstance(up.check(get=world.get, current="2.0.3", keys={"test-1": b"\x01" * 32}), up.Failed)


def test_a_licence_style_signature_without_the_label_is_refused(tmp_path):
    def bare(files):
        key = um.Ed25519PrivateKey.from_private_bytes(um._unb64(world.jwk["d"]))
        files["UPDATE.json.sig"] = base64.b64encode(key.sign(files["UPDATE.json"]))
    world = World(tmp_path)
    bare(world.files)
    assert isinstance(world.check(), up.Failed)


def test_a_release_without_a_manifest_or_the_network_down_fails_plainly(tmp_path):
    world = World(tmp_path)
    world.release = json.dumps({"assets": []}).encode()
    assert "no signed update" in world.check().reason

    def down(url):
        raise up.UpdateError("Lightning could not reach GitHub. Check the internet connection.")
    result = up.check(get=down, current="2.0.3", keys=world.keys)
    assert isinstance(result, up.Failed) and "internet" in result.reason
    assert isinstance(up.check(get=lambda url: b"<html>", current="2.0.3", keys=world.keys), up.Failed)


def test_verify_agrees_with_the_packaging_tool(tmp_path):
    world = World(tmp_path)
    raw, sig = world.files["UPDATE.json"], world.files["UPDATE.json.sig"].decode().strip()
    assert up.verify_manifest(raw, sig, world.keys) == um.verify(raw, sig, world.keys, tag=f"v{VERSION}")
    for bad in (raw + b" ", raw.replace(b"2.0.4", b"2.0.5")):
        with pytest.raises(up.UpdateError):
            up.verify_manifest(bad, sig, world.keys)
        with pytest.raises(um.ManifestError):
            um.verify(bad, sig, world.keys)
    assert up.load_keys().keys() >= {"store-2026-1"}


def test_download_checks_size_and_hash_and_reports_progress(tmp_path):
    world = World(tmp_path)
    found = available(world)
    seen = []
    path = up.download(found, tmp_path / "updates", stream=world.stream, free_bytes=lambda p: 10**12,
                       progress=lambda done, total: seen.append((done, total)))
    assert path == tmp_path / "updates" / VERSION / ZIP and path.read_bytes() == world.zip
    assert seen[-1] == (len(world.zip), len(world.zip))


def test_a_download_that_differs_is_deleted(tmp_path):
    world = World(tmp_path)
    found = available(world)
    world.files[ZIP] = world.zip[:-1] + bytes([world.zip[-1] ^ 1])  # same size, one bit off
    with pytest.raises(up.UpdateError, match="does not match"):
        up.download(found, tmp_path / "u", stream=world.stream, free_bytes=lambda p: 10**12)
    assert not (tmp_path / "u" / VERSION / ZIP).exists()
    world.files[ZIP] = world.zip + b"x"
    with pytest.raises(up.UpdateError, match="larger"):
        up.download(found, tmp_path / "u", stream=world.stream, free_bytes=lambda p: 10**12)
    assert not (tmp_path / "u" / VERSION / ZIP).exists()


def test_no_space_means_nothing_is_downloaded(tmp_path):
    world = World(tmp_path)
    found = available(world)
    with pytest.raises(up.UpdateError, match="free space"):
        up.download(found, tmp_path / "u", stream=lambda url: pytest.fail("downloaded"), free_bytes=lambda p: 3 * found.size - 1)
    up.download(found, tmp_path / "u", stream=world.stream, free_bytes=lambda p: 3 * found.size)


def staged(tmp_path, zip_bytes, run=None):
    path = tmp_path / "z" / ZIP
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(zip_bytes)
    return up.stage(path, VERSION, run=run or (lambda cmd, cwd: _ok(cmd)))


def _ok(cmd):
    Path(cmd[cmd.index("--report") + 1]).write_text(json.dumps({"ok": True}))
    return 0


def test_stage_extracts_hashes_every_file_and_runs_the_self_check(tmp_path):
    calls = []
    root = staged(tmp_path, make_zip(), run=lambda cmd, cwd: calls.append((cmd, cwd)) or _ok(cmd))
    assert (root / "Lightning.exe").read_bytes() == b"exe" and root == tmp_path / "z" / "staged"
    lines = (root / "FILES.sha256").read_text().splitlines()
    assert f"{hashlib.sha256(b'dll').hexdigest()}  lib/a.dll" in lines and len(lines) == 3
    [(cmd, cwd)] = calls
    assert cmd[1:3] == ["--self-check", "--report"] and Path(cmd[0]) == root / "Lightning.exe" and cwd == root


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a/../../evil", "C:/x.txt", "a\\b.txt"])
def test_zip_slip_is_refused(tmp_path, name):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Lightning.exe", b"exe")
        archive.writestr(name, b"x")
    with pytest.raises(up.UpdateError, match="unsafe path"):
        staged(tmp_path, buffer.getvalue())
    assert not (tmp_path / "z" / "staged").exists() and not (tmp_path / "evil.txt").exists()


def test_a_symbolic_link_is_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        link = zipfile.ZipInfo("Lightning.exe")
        link.external_attr = 0o120777 << 16
        archive.writestr(link, "elsewhere")
    with pytest.raises(up.UpdateError, match="unsafe path"):
        staged(tmp_path, buffer.getvalue())


def test_missing_exe_or_wrong_version_or_failed_self_check_is_refused(tmp_path):
    with pytest.raises(up.UpdateError, match="Lightning.exe"):
        staged(tmp_path, make_zip({"BUILD_INFO.txt": b"Lightning 2.0.4"}))
    with pytest.raises(up.UpdateError, match="version it claims"):
        staged(tmp_path, make_zip({"Lightning.exe": b"e", "BUILD_INFO.txt": b"Lightning 2.0.40 for Windows"}))
    with pytest.raises(up.UpdateError, match="its own check"):
        staged(tmp_path, make_zip(), run=lambda cmd, cwd: 1)
    with pytest.raises(up.UpdateError, match="its own check"):
        staged(tmp_path, make_zip(), run=lambda cmd, cwd: (Path(cmd[-1]).write_text('{"ok": false}'), 0)[1])
    with pytest.raises(up.UpdateError, match="damaged"):
        staged(tmp_path, b"not a zip")
    assert not (tmp_path / "z" / "staged").exists()
