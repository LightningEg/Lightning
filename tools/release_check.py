"""Checks to run before tagging a release. Read-only; prints findings, exits 1 when there are any.

    python tools/release_check.py

Checks: the version agrees in pyproject.toml, lightning/__init__.py and the README; the tag it implies; the working
tree is clean, on main and level with origin; LICENSE and CONTRIBUTING.md exist; the current version has release notes in
ai/changelog/ and nothing waits in UNRELEASED.md; no tracked file looks like a secret or private data (keys, keystores, databases other than the one
encrypted test fixture, tokens, personal emails); and no TODO/FIXME/XXX markers sit in shipped code.
It does not run the tests: the release skill does that next.

    python tools/release_check.py --artifacts Lightning-v2.3.2-Windows-x64.zip Lightning-2.3.2-1224-6aa97680.apk

After publishing, inspects the downloaded archives (and the Chaquopy .imy archives inside an APK): no .git/, tests/,
database, key store, recovery code, .env or Documents/Lightning path, nothing shaped like a secret, and an APK asks for
exactly the permissions in packaging/android-permissions.txt. The one allowed exception is the dummy round-trip
fixture (tests/fixtures/roundtrip) the phone's on-device check opens as `roundtrip_fixture/`.
"""
from __future__ import annotations

import io
import re
import subprocess
import zipfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET = re.compile(
    r"(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[bp]-[A-Za-z0-9-]{10,})")
PRIVATE_FILES = re.compile(r"\.(p12|jks|keystore|pem|key|pfx|sqlite|sqlite3|env)$|(^|/)\.env|ANDROID_TEST_KEYSTORE")
ALLOWED_DB = {"tests/fixtures/roundtrip/profile.db"}  # encrypted, dummy data
THIRD_PARTY = ("packaging/notices/", "requirements/")
# A published archive never carries these. Public-by-design: lightning/security/*_keys.json (pinned public keys)
# and the CA bundle cacert.pem; the dummy round-trip fixture is the only database, key file and recovery code.
ARCHIVE_PRIVATE = re.compile(
    r"((^|/)\.git/|(^|/)tests/|\.(db|sqlite3?|db-wal|db-shm|jks|p12|pfx|keystore|key|bak|log)$|(^|/)recovery\.txt$|"
    r"(^|/)keys\.json$|(^|/)\.env($|\.)|Documents/Lightning/)", re.IGNORECASE)
ARCHIVE_ALLOWED = re.compile(r"^roundtrip_fixture/(profile\.db|keys\.json|recovery\.txt|expected\.json)$")
PUBLIC_PEM = re.compile(r"(^|/)(cacert|certifi/cacert)\.pem$")
# Texts that only name a key format (checks in code and libraries) are not keys: a real key has base64 after it.
ARCHIVE_SECRET = re.compile(
    rb"(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|xox[bp]-[A-Za-z0-9-]{10,}|"
    rb"sb_secret_[A-Za-z0-9_-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----\s+[A-Za-z0-9+/]{40,})")
PERMISSION = re.compile(rb"android\.permission\.[A-Z_]+")
SERVICE_GUARDS = {"android.permission.BIND_JOB_SERVICE", "android.permission.BIND_QUICK_SETTINGS_TILE"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def versions() -> list[str]:
    toml = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    source = (ROOT / "lightning" / "__init__.py").read_text(encoding="utf-8")
    init = re.search(r'__version__ = "([^"]+)"', source).group(1)
    display = re.search(r'DISPLAY_VERSION = "([^"]+)"', source).group(1)
    readme = re.search(r"source version is \*\*v?([^*]+)\*\*", (ROOT / "README.md").read_text(encoding="utf-8"))
    norm = lambda v: v
    out = []
    if toml != init:
        out.append(f"pyproject.toml has {toml} but lightning/__init__.py has {init}")
    if norm(display) != norm(toml):
        out.append(f"the app displays {display} but pyproject.toml has {toml}")
    if readme and norm(readme.group(1)) != norm(toml):
        out.append(f"README names {readme.group(1)} but pyproject.toml has {toml}")
    tag = "v" + toml
    print(f"version {toml} -> tag {tag}")
    return out


def tree() -> list[str]:
    out = []
    if git("status", "--porcelain"):
        out.append("the working tree has uncommitted changes")
    if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        out.append("not on main")
    git("fetch", "-q", "origin", "main")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        out.append("HEAD is not level with origin/main (pull or push first)")
    return out


def files() -> list[str]:
    out = [f"missing {name}" for name in ("LICENSE", "CONTRIBUTING.md") if not (ROOT / name).exists()]
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    notes = ROOT / "ai" / "changelog" / f"{version}.md"
    if not notes.exists() or not re.search(r"^- ", notes.read_text(encoding="utf-8").split("## Detail", 1)[0], re.M):
        out.append(f"ai/changelog/{version}.md has no notes: python tools/release_notes.py cut {version}")
    if (ROOT / "ai" / "changelog" / "UNRELEASED.md").exists():
        out.append("ai/changelog/UNRELEASED.md still holds entries: python tools/release_notes.py cut " + version)
    return out


def private() -> list[str]:
    out = []
    for name in git("ls-files").splitlines():
        if PRIVATE_FILES.search(name) or (name.endswith(".db") and name not in ALLOWED_DB):
            out.append(f"tracked file looks private: {name}")
            continue
        if name.startswith(THIRD_PARTY) or name.endswith((".png", ".woff2", ".ico", ".zip", ".lock", ".jar")):
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if SECRET.search(text):
            out.append(f"{name} contains something shaped like a secret")
        if name.startswith("lightning/") and name.endswith(".py") and re.search(r"#\s*(TODO|FIXME|XXX)\b", text):
            out.append(f"{name} has a TODO/FIXME/XXX marker")
    return out


def archive_entries(archive: zipfile.ZipFile, prefix: str = ""):
    """(name, bytes) of every file, descending into the Chaquopy .imy archives inside an APK."""
    for info in archive.infolist():
        if info.is_dir():
            continue
        data = archive.read(info)
        if info.filename.endswith(".imy") and zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as inner:
                yield from archive_entries(inner, prefix + info.filename + "!")
        else:
            yield prefix + info.filename, data


def manifest_permissions(manifest: bytes) -> set[str]:
    """Permissions the APK asks for, read from the binary manifest's UTF-16 string pool, without the service guards."""
    found = PERMISSION.findall(manifest.decode("utf-16-le", "ignore").encode()) + PERMISSION.findall(manifest)
    return {name.decode() for name in found} - SERVICE_GUARDS


def artifact(path: Path) -> list[str]:
    out = []
    with zipfile.ZipFile(path) as archive:
        entries = dict(archive_entries(archive))
    for name, data in entries.items():
        inner = name.rsplit("!", 1)[-1]
        if ARCHIVE_PRIVATE.search(inner) and not ARCHIVE_ALLOWED.match(inner):
            out.append(f"{path.name}: {name} must not be published")
        if inner.endswith(".pem") and not PUBLIC_PEM.search(inner):
            out.append(f"{path.name}: {name} is a certificate or key file")
        if ARCHIVE_SECRET.search(data):
            out.append(f"{path.name}: {name} contains something shaped like a secret")
    if path.suffix == ".apk":
        wanted = set(re.findall(r"^android\.permission\.[A-Z_]+", (ROOT / "packaging" / "android-permissions.txt")
                                .read_text(encoding="utf-8"), re.M))
        asked = manifest_permissions(entries.get("AndroidManifest.xml", b""))
        out += [f"{path.name}: asks for {name}, which packaging/android-permissions.txt does not list"
                for name in sorted(asked - wanted)]
        out += [f"{path.name}: lacks {name}" for name in sorted(wanted - asked)]
    print(f"{path.name}: {len(entries)} files inspected")
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["--artifacts"]:
        findings = [line for name in sys.argv[2:] for line in artifact(Path(name))]
        print("\n".join(findings) or "nothing private in the published archives")
        sys.exit(1 if findings or len(sys.argv) < 3 else 0)
    findings = [*versions(), *tree(), *files(), *private()]
    print("\n".join(findings) or "ready for the tests")
    sys.exit(1 if findings else 0)
