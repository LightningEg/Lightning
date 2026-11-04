"""Write requirements/android.lock: every Python package the phone app installs, each as one exact file
(a URL and its SHA-256), so every build of one commit carries identical code.

    python tools/android_lock.py android-wheels-r<run> <that release's SHA256SUMS>

The four native wheels (cffi, cryptography, pydantic-core, sqlcipher3) come from that release of this
repository, published by android-native-wheels.yml with publish_run. Every other package is the PyPI wheel
for CPython 3.13 on arm64 Android of the version uv resolves from requirements/android.in. Needs uv and
network access to PyPI. The phone build installs the lock with pip's --no-index and --require-hashes, so
nothing outside it can be installed, and packaging/phone_build.py checks the APK carries exactly this set.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "requirements" / "android.in"
LOCK = ROOT / "requirements" / "android.lock"
REPOSITORY = "elfekimuhammed/Lightning"
NATIVE = ("cffi", "cryptography", "pydantic-core", "sqlcipher3")
# Upstream's unchanged portable wheel: MIT-licensed, no Android extension required.
PORTABLE = {"rapidfuzz": ("3.14.3", "https://github.com/LightningEg/Lightning/raw/835b0bb48f8f134f73a0d754a3b5344e317931b0/packaging/third-party/rapidfuzz-3.14.3-py3-none-any.whl", "8e300f5974c411be699fd53f775fffbe94204a012a3091e23e1a300c2fc8ebad")}
PYTHON, API = (3, 13), 24


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def wheel_parts(filename: str) -> tuple[str, str, list[str], str, list[str]]:
    """(name, version, python tags, abi, platform tags) of a wheel file name."""
    parts = filename[: -len(".whl")].split("-")
    if not filename.endswith(".whl") or len(parts) not in (5, 6):
        raise ValueError(f"not a wheel: {filename}")
    name, version, pythons, abi, platforms = parts[0], parts[1], parts[-3], parts[-2], parts[-1]
    return normalize(name), version, pythons.split("."), abi, platforms.split(".")


def rank(filename: str) -> tuple[int, int] | None:
    """How well a wheel fits CPython 3.13 on arm64 Android at API 24 (higher is better), or None."""
    _, _, pythons, abi, platforms = wheel_parts(filename)
    android = any(re.fullmatch(r"android_(\d+)_arm64_v8a", p) and int(p.split("_")[1]) <= API for p in platforms)
    if not android and "any" not in platforms:
        return None
    cp = f"cp{PYTHON[0]}{PYTHON[1]}"
    if abi == cp and cp in pythons:
        abi_rank = 3
    elif abi == "abi3" and any(re.fullmatch(r"cp3(\d+)", p) and int(p[3:]) <= PYTHON[1] for p in pythons):
        abi_rank = 2
    elif abi == "none" and any(p in ("py3", f"py{PYTHON[0]}{PYTHON[1]}", cp) for p in pythons):
        abi_rank = 1
    else:
        return None
    return (1 if android else 0, abi_rank)


def pinned(text: str) -> dict[str, str]:
    """name -> version for the `name==version` lines of a requirements text."""
    found = {}
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if match := re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;\\]+)", line):
            found[normalize(match[1])] = match[2]
    return found


def resolve() -> dict[str, str]:
    """The pure-Python packages (name -> version) uv resolves for arm64 Android from android.in."""
    command = ["uv", "pip", "compile", str(SOURCE), "--python-version", f"{PYTHON[0]}.{PYTHON[1]}",
               "--python-platform", "aarch64-linux-android", "--no-header", "--no-annotate", "--quiet"]
    for name in (*NATIVE, *PORTABLE):
        command += ["--no-emit-package", name]
    return pinned(subprocess.run(command, check=True, capture_output=True, text=True).stdout)


def pypi_file(name: str, version: str) -> tuple[str, str]:
    """(URL, SHA-256) of the PyPI wheel of name==version that fits the phone best."""
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
        files = json.load(response)["urls"]
    fitting = [(rank(f["filename"]), f) for f in files if f["filename"].endswith(".whl")]
    fitting = [(r, f) for r, f in fitting if r is not None]
    if not fitting:
        raise SystemExit(f"{name}=={version} has no wheel for CPython 3.13 on arm64 Android on PyPI")
    best = max(fitting, key=lambda item: item[0])[1]
    return best["url"], best["digests"]["sha256"]


def native_files(tag: str, sums: str, wanted: dict[str, str]) -> dict[str, tuple[str, str]]:
    """name -> (URL, SHA-256) of the four native wheels, checked against android.in's versions."""
    found = {}
    for line in sums.splitlines():
        if not line.strip():
            continue
        digest, filename = line.split()
        name, version, *_ = wheel_parts(filename.lstrip("*"))
        if name in found:
            raise SystemExit(f"two {name} wheels in SHA256SUMS")
        if wanted.get(name) != version:
            raise SystemExit(f"{filename} does not match android.in ({name}=={wanted.get(name)})")
        if rank(filename) is None or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SystemExit(f"{filename} does not fit the phone, or its SHA-256 is malformed")
        found[name] = (f"https://github.com/{REPOSITORY}/releases/download/{tag}/{filename.lstrip('*')}", digest)
    if sorted(found) != sorted(NATIVE):
        raise SystemExit(f"SHA256SUMS must hold exactly {', '.join(NATIVE)}; it holds {', '.join(sorted(found))}")
    return found


def lock_text(tag: str, files: dict[str, tuple[str, str]]) -> str:
    lines = ["# Generated by tools/android_lock.py from requirements/android.in; do not edit by hand.",
             f"# android-wheels: {tag}",
             "# Every package the phone app installs, as one exact file. Installed with --no-index."]
    for name in sorted(files):
        url, digest = files[name]
        lines += [f"{name} @ {url} \\", f"    --hash=sha256:{digest}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not re.fullmatch(r"android-wheels-r\d+", argv[0]):
        print(__doc__)
        return 2
    tag, sums = argv[0], Path(argv[1]).read_text()
    wanted = pinned(SOURCE.read_text())
    files = native_files(tag, sums, wanted)
    for name, (version, url, digest) in PORTABLE.items():
        if wanted.get(name) != version:
            raise SystemExit(f"Portable {{name}} input does not match android.in")
        files[name] = (url, digest)
    for name, version in resolve().items():
        files[name] = pypi_file(name, version)
    LOCK.write_text(lock_text(tag, files), encoding="utf-8")
    print(f"Wrote {LOCK.relative_to(ROOT)}: {len(files)} packages, native wheels from {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
