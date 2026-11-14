"""Check for, download and stage a Windows update (NF-9B2). Pure Python: no window, no database, testable on Linux.

Nothing here runs unless the person pressed "Check for updates". The only requests are GitHub's release API and the
asset downloads, with `User-Agent: Lightning/<version>`. Nothing about the person or their data is sent. Everything
is verified against the signed manifest (`UPDATE.json` + `UPDATE.json.sig`, see ai/ARCHITECTURE.md "Build and
release") before it is trusted; the logic of `verify_manifest` mirrors packaging/update_manifest.py (a test keeps the
two agreeing). The functions are meant to run on a worker thread, never on the database thread.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import stat
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from lightning import DISPLAY_VERSION

RELEASES_URL = "https://api.github.com/repos/LightningEg/Lightning-downloads/releases/latest"
LABEL = b"lightning-update-v1:"
KEYS_FILE = Path(__file__).resolve().parents[1] / "security" / "update_keys.json"
FIELDS = {"format", "version", "zip", "sha256", "size", "released", "key_id"}
MAX_FILES, MAX_UNPACKED = 5_000, 1_500_000_000
SPACE_FACTOR = 3  # the ZIP, its extracted copy and room to spare


class UpdateError(Exception):
    """A plain reason an update step failed, shown to the person."""


@dataclass(frozen=True)
class UpToDate:
    pass


@dataclass(frozen=True)
class Available:
    version: str
    size: int
    zip_name: str
    sha256: str
    zip_url: str


@dataclass(frozen=True)
class Failed:
    reason: str


def load_keys(path: Path = KEYS_FILE) -> dict[str, bytes]:
    data = json.loads(path.read_text(encoding="utf-8")).get("keys", {})
    return {kid: base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)) for kid, raw in data.items()}


def version_tuple(text: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", text or ""):
        raise UpdateError("The update information is not in the expected form.")
    return tuple(int(part) for part in text.split("."))


def verify_manifest(raw: bytes, signature: str | bytes, keys: dict[str, bytes]) -> dict:
    """The manifest if the signature over LABEL + its exact bytes is good, else UpdateError."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise UpdateError("The update information is not readable.") from None
    if not isinstance(data, dict) or set(data) != FIELDS or not isinstance(data["key_id"], str):
        raise UpdateError("The update information is not in the expected form.")
    key = keys.get(data["key_id"])
    if key is None:
        raise UpdateError("The update is signed with a key this Lightning does not know.")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(base64.b64decode(signature, validate=True), LABEL + raw)
    except (InvalidSignature, ValueError):
        raise UpdateError("The update’s signature does not match, so it was not trusted.") from None
    version, name, sha, size = data["version"], data["zip"], data["sha256"], data["size"]
    version_tuple(version)
    if (data["format"] != 1 or name != f"Lightning-v{version}-Windows-x64.zip"
            or not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha))
            or not (isinstance(size, int) and not isinstance(size, bool) and size > 0)):
        raise UpdateError("The update information is not in the expected form.")
    return data


def http_get(url: str, *, limit: int = 1_000_000, retries: int = 3, timeout: float = 30.0) -> bytes:
    """GET with Lightning's User-Agent; retries network and server errors only (as lightning/market/http.py)."""
    for attempt in range(1, retries + 1):
        try:
            with urlopen(_request(url), timeout=timeout) as response:
                return response.read(limit)
        except HTTPError as error:
            if error.code < 500 or attempt == retries:
                raise UpdateError("GitHub answered with an error. Try again later.") from None
        except (URLError, TimeoutError, OSError):
            if attempt == retries:
                raise UpdateError("Lightning could not reach GitHub. Check the internet connection.") from None
        time.sleep(2 * attempt)
    raise UpdateError("Lightning could not reach GitHub.")  # pragma: no cover


def http_stream(url: str, *, chunk: int = 1 << 20, timeout: float = 30.0) -> Iterator[bytes]:
    try:
        with urlopen(_request(url), timeout=timeout) as response:
            while block := response.read(chunk):
                yield block
    except HTTPError:
        raise UpdateError("GitHub answered with an error. Try again later.") from None
    except (URLError, TimeoutError, OSError):
        raise UpdateError("The download was interrupted.") from None


def _request(url: str) -> Request:
    if not url.startswith("https://"):
        raise UpdateError("Only secure downloads are allowed.")
    return Request(url, headers={"User-Agent": f"Lightning/{DISPLAY_VERSION}", "Accept": "application/vnd.github+json, */*"})


def check(*, get: Callable[[str], bytes] = http_get, current: str = DISPLAY_VERSION,
          keys: dict[str, bytes] | None = None, releases_url: str = RELEASES_URL) -> UpToDate | Available | Failed:
    """Newest stable release: signature verified, then compared with this version."""
    try:
        release = json.loads(get(releases_url))
        assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
        if "UPDATE.json" not in assets or "UPDATE.json.sig" not in assets:
            raise UpdateError("The newest release has no signed update information.")
        manifest = verify_manifest(get(assets["UPDATE.json"]), get(assets["UPDATE.json.sig"]).decode("ascii", "replace").strip(),
                                   load_keys() if keys is None else keys)
        if manifest["zip"] not in assets:
            raise UpdateError("The newest release does not hold its update file.")
        if version_tuple(manifest["version"]) <= version_tuple(current):
            return UpToDate()
        return Available(manifest["version"], manifest["size"], manifest["zip"], manifest["sha256"], assets[manifest["zip"]])
    except UpdateError as error:
        return Failed(str(error))
    except (ValueError, KeyError, TypeError):
        return Failed("GitHub’s answer was not in the expected form.")


def download(found: Available, folder: Path, *, stream: Callable[[str], Iterator[bytes]] = http_stream,
             free_bytes: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free,
             progress: Callable[[int, int], None] = lambda done, total: None) -> Path:
    """Fetch the ZIP into `folder/<version>/`; its size and SHA-256 must equal the signed manifest, else it is deleted."""
    target = folder / found.version
    target.mkdir(parents=True, exist_ok=True)
    if free_bytes(target) < SPACE_FACTOR * found.size:
        raise UpdateError("There is not enough free space on this PC for the update.")
    path = target / found.zip_name
    digest, done = hashlib.sha256(), 0
    try:
        with path.open("wb") as out:
            for block in stream(found.zip_url):
                done += len(block)
                if done > found.size:
                    raise UpdateError("The download is larger than the signed update, so it was discarded.")
                digest.update(block)
                out.write(block)
                progress(done, found.size)
        if done != found.size or digest.hexdigest() != found.sha256:
            raise UpdateError("The download does not match the signed update, so it was discarded.")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _safe_members(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    infos = archive.infolist()
    if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_UNPACKED:
        raise UpdateError("The update file is not shaped like a Lightning release.")
    members = []
    for info in infos:
        name = info.filename
        path = PurePosixPath(name)
        if (name.startswith(("/", "\\")) or "\\" in name or ":" in name or ".." in path.parts
                or (info.external_attr >> 16) and stat.S_ISLNK(info.external_attr >> 16)):
            raise UpdateError("The update holds an unsafe path, so it was not used.")
        members.append((info, path))
    return members


def stage(zip_path: Path, version: str, *, run: Callable[[list[str], Path], int] | None = None) -> Path:
    """Extract next to the ZIP into `staged/`, check it is this release, hash every file, and run its --self-check."""
    root = zip_path.parent / "staged"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = _safe_members(archive)
            files = [(i, p) for i, p in members if not i.is_dir()]
            tops = {p.parts[0] for _, p in files if len(p.parts) > 1}
            strip = 1 if len(tops) == 1 and not any(len(p.parts) == 1 for _, p in files) else 0
            for info, path in files:
                dest = root.joinpath(*path.parts[strip:])
                if root.resolve() not in dest.resolve().parents:
                    raise UpdateError("The update holds an unsafe path, so it was not used.")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
        if not (root / "Lightning.exe").is_file():
            raise UpdateError("The update does not contain Lightning.exe, so it was not used.")
        info_file = root / "BUILD_INFO.txt"
        if not info_file.is_file() or not re.search(rf"(?<![\d.]){re.escape(version)}(?![\d.])", info_file.read_text(encoding="utf-8", errors="replace")):
            raise UpdateError("The update does not say it is the version it claims, so it was not used.")
        lines = sorted(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}"
                       for p in root.rglob("*") if p.is_file())
        (root / "FILES.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = zip_path.parent / "check.json"
        code = (run or _run)([str(root / "Lightning.exe"), "--self-check", "--report", str(report)], root)
        try:
            ok = code == 0 and json.loads(report.read_text(encoding="utf-8")).get("ok") is True
        except (OSError, ValueError):
            ok = False
        if not ok:
            raise UpdateError("The new version did not pass its own check on this PC, so it was not installed.")
    except zipfile.BadZipFile:
        shutil.rmtree(root, ignore_errors=True)
        raise UpdateError("The update file is damaged.") from None
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root


def _run(command: list[str], cwd: Path) -> int:
    try:
        return subprocess.run(command, cwd=cwd, timeout=180, check=False).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1
