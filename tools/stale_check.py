"""Find stale things in the repository. Read-only; prints findings, exits 1 when there are any.

    python tools/stale_check.py [--days 7]

Checks: NOW.md messages and claims older than --days; Markdown links to files that no longer exist; designs in
issues/ that say they are built; new bugs untouched for 30 days; branches already merged into main (to delete) or ahead of it (unmerged work);
the README version against pyproject; and the guideline copies against a sibling Lightning_website checkout.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip()


def old(day: str, days: int) -> bool:
    return (date.today() - date.fromisoformat(day)).days > days


def hand_off(days: int) -> list[str]:
    out, text = [], (ROOT / "NOW.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        found = re.search(r"\d{4}-\d{2}-\d{2}", line)
        if not found:
            continue
        if line.startswith("- **To") and old(found.group(0), days):
            out.append(f"NOW.md message from {found.group(0)}: {line[:70]}")
        elif line.startswith("|") and re.search(r"\| *\d{4}-\d{2}-\d{2} *\|$", line) and old(found.group(0), days):
            out.append(f"NOW.md claim since {found.group(0)}: {line[:70]}")
    return out


def dead_links() -> list[str]:
    out = []
    for path in [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "skills").rglob("*.md")]:
        for target in re.findall(r"\]\(([^)#\s]+)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).exists():
                out.append(f"{path.relative_to(ROOT)} links to missing {target}")
    return out


def built_proposals() -> list[str]:
    out = []
    for path in (ROOT / "issues").glob("*/*.md"):
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:16])
        status = re.search(r"Status:\*\*([^.;\n]*)", head, re.I)  # a design's own status line, first clause only
        clause = status.group(1).lower() if status else ""
        if re.search(r"\b(built|done|shipped)\b", clause) and not re.search(r"\b(not|started|partly|remaining)\b", clause):
            out.append(f"{path.relative_to(ROOT)} says it is built: move what holds into Architecture and delete it")
    return out


def old_reports(days: int = 30) -> list[str]:
    """New bugs nobody has looked at for a month; one waiting for a person on GitHub (github:) is left alone."""
    out = []
    for path in (ROOT / "issues").glob("*/*.md"):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^created:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
        fresh = re.search(r"^status:\s*new\s*$", text, re.M) and re.search(r"^type:\s*bug\s*$", text, re.M)
        if match and fresh and old(match.group(1), days) and not re.search(r"^github:", text, re.M):
            out.append(f"{path.relative_to(ROOT).as_posix()} is a new bug nobody has looked at since {match.group(1)}")
    return out


def branches() -> list[str]:
    merged, ahead = [], []
    for name in git("branch", "-r", "--format=%(refname:short)").splitlines():
        if name.endswith(("/HEAD", "/main")) or "/" not in name:
            continue
        count = git("rev-list", "--count", f"origin/main..{name}")
        (merged if count == "0" else ahead).append(name.removeprefix("origin/"))
    out = []
    if merged:
        out.append(f"{len(merged)} branches already merged into main, safe to delete: {', '.join(merged[:6])}{' ...' if len(merged) > 6 else ''}")
    if ahead:
        out.append(f"{len(ahead)} branches hold commits not in main (finished, or abandoned?): {', '.join(ahead[:6])}{' ...' if len(ahead) > 6 else ''}")
    return out


def versions() -> list[str]:
    toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"', toml, re.M).group(1)
    named = re.search(r"source version is \*\*v?([^*]+)\*\*", (ROOT / "README.md").read_text(encoding="utf-8"))
    if not named:
        return []
    norm = lambda v: re.sub(r"[-.]?(beta|b)[.]?", "b", v)
    return [] if norm(named.group(1)) == norm(version) else [f"README names version {named.group(1)} but pyproject has {version}"]


def guideline_copies() -> list[str]:
    site = ROOT.parent / "Lightning_website" / "guideline"
    if not site.is_dir():
        return []
    return [f"guideline/{p.name} differs from Lightning_website" for p in (ROOT / "guideline").iterdir()
            if p.is_file() and (site / p.name).exists() and (site / p.name).read_bytes() != p.read_bytes()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    findings = [*hand_off(args.days), *dead_links(), *built_proposals(), *old_reports(), *branches(), *versions(), *guideline_copies()]
    print("\n".join(findings) or "nothing stale")
    sys.exit(1 if findings else 0)
