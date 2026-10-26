"""Checks to run before tagging a release. Read-only; prints findings, exits 1 when there are any.

    python tools/release_check.py

Checks: the version agrees in pyproject.toml, lightning/__init__.py and the README; the tag it implies; the working
tree is clean, on main and level with origin; LICENSE and CONTRIBUTING.md exist; the changelog has entries under
Unreleased or the current version; no tracked file looks like a secret or private data (keys, keystores, databases other than the one
encrypted test fixture, tokens, personal emails); and no TODO/FIXME/XXX markers sit in shipped code.
It does not run the tests: the release skill does that next.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET = re.compile(
    r"(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[bp]-[A-Za-z0-9-]{10,})")
PRIVATE_FILES = re.compile(r"\.(p12|jks|keystore|pem|key|pfx|sqlite|sqlite3|env)$|(^|/)\.env|ANDROID_TEST_KEYSTORE")
ALLOWED_DB = {"tests/fixtures/roundtrip/profile.db"}  # encrypted, dummy data
THIRD_PARTY = ("packaging/notices/", "requirements/")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def versions() -> list[str]:
    toml = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    source = (ROOT / "lightning" / "__init__.py").read_text(encoding="utf-8")
    init = re.search(r'__version__ = "([^"]+)"', source).group(1)
    display = re.search(r'DISPLAY_VERSION = "([^"]+)"', source).group(1)
    readme = re.search(r"source version is \*\*v?([^*]+)\*\*", (ROOT / "README.md").read_text(encoding="utf-8"))
    norm = lambda v: re.sub(r"[-.]?(beta|b)[.]?", "b", v)
    out = []
    if toml != init:
        out.append(f"pyproject.toml has {toml} but lightning/__init__.py has {init}")
    if norm(display) != norm(toml):
        out.append(f"the app displays {display} but pyproject.toml has {toml}")
    if readme and norm(readme.group(1)) != norm(toml):
        out.append(f"README names {readme.group(1)} but pyproject.toml has {toml}")
    tag = "v" + re.sub(r"b(\d+)$", r"-beta.\1", toml)
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
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    block = re.split(r"^## \[Unreleased\]", changelog, maxsplit=1, flags=re.M)[-1].split("\n## [", 1)[0]
    if not re.search(r"^- \d{4}-", block, re.M):
        version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
        released = re.search(r"^## \[" + re.escape(version) + r"\][^\n]*\n(.*?)(?=^## \[|\Z)", changelog, re.M | re.S)
        if not released or not re.search(r"^- \d{4}-", released.group(1), re.M):
            out.append("CHANGELOG.md has no entries under Unreleased or the current version")
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


if __name__ == "__main__":
    findings = [*versions(), *tree(), *files(), *private()]
    print("\n".join(findings) or "ready for the tests")
    sys.exit(1 if findings else 0)
