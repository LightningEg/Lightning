"""Release notes without a shared changelog file: written once, in the commit, and generated into two readable places.

A commit (any commit in a pull request; the squash keeps them all) ends with two trailers:

    Release-note: own: Converting EGP to dollars no longer changes your net worth.
    Detail: BT-5J. Convert asks once when the rate is 20% off the market rate; the swapped amounts valued every dollar at 0.02 EGP.

`Release-note` is one plain sentence for a person, prefixed with the pillar (docs/README.md), or `none` for a change nobody
would notice. `Detail` is what an AI needs to continue: what changed, where, why, in one line.

    python tools/release_notes.py                  # rewrite RELEASES.md from ai/changelog/*.md
    python tools/release_notes.py --check          # exit 1 if RELEASES.md is out of date
    python tools/release_notes.py recent           # what is unreleased: the trailers since the last release
    python tools/release_notes.py cut 1.5.5        # write ai/changelog/1.5.5.md from those trailers, then RELEASES.md
    python tools/release_notes.py check-pr origin/main   # CI: the pull request's commits carry both trailers

`cut` and `recent` start from the newest tag `v*`, or `--from REF` when there is none. Entries made before trailers existed
wait in ai/changelog/UNRELEASED.md and join the next cut.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "ai" / "changelog"
RELEASES = ROOT / "RELEASES.md"
NOTE = re.compile(r"^Release-note:[ \t]*(.+?)[ \t]*$", re.M)
DETAIL = re.compile(r"^Detail:[ \t]*(.+?)[ \t]*$", re.M)
CODE = re.compile(r"\b((?:B[VT]|I[VT]|NF|OW)-\d+[A-Z]+\d*)\b")
PR = re.compile(r"\(#(\d+)\)\s*$")


def _pillars() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("issues_tool", Path(__file__).resolve().parent / "issues.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["issues_tool"] = module
    spec.loader.exec_module(module)
    return module.PILLARS


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def version_key(name: str) -> tuple:
    """1.5.4 > 1.5.2 > 1.1.0b1; a pre-release sorts below its release."""
    major, minor, patch, pre = re.match(r"(\d+)\.(\d+)\.(\d+)(.*)", name).groups()
    return int(major), int(minor), int(patch), 0 if pre else 1, pre


def parse_note(text: str) -> tuple[str, str] | None:
    """(pillar, sentence) from `own: sentence`, or None for `none`. Raises ValueError on anything else."""
    if text.strip().lower() == "none":
        return None
    pillar, sep, sentence = text.partition(":")
    if not sep or pillar.strip() not in _pillars() or not sentence.strip():
        raise ValueError(f"Release-note must be `<pillar>: one sentence` or `none` (pillars: {', '.join(_pillars())}): {text!r}")
    return pillar.strip(), sentence.strip()


def latest_tag() -> str | None:
    tags = [t for t in git("tag", "--list", "v*").split() if re.fullmatch(r"v\d+\.\d+\.\d+.*", t)]
    return max(tags, key=lambda t: version_key(t[1:])) if tags else None


def commits(since: str | None, first_parent: bool = True) -> list[dict]:
    """Commits since a ref. On main, history is squash commits, so first-parent. A pull request's CI checks out a merge commit
    whose first parent is the base, so check-pr reads every commit in the range instead."""
    rng = f"{since}..HEAD" if since else "HEAD"
    raw = git("log", *(["--first-parent"] if first_parent else []), "--format=%H%x1f%ad%x1f%s%x1f%b%x1e", "--date=short", rng)
    out = []
    for block in raw.split("\x1e"):
        if not block.strip():
            continue
        sha, day, subject, body = block.strip("\n").split("\x1f", 3)
        pr = PR.search(subject)
        out.append({"sha": sha[:8], "date": day, "subject": subject, "pr": pr.group(1) if pr else "",
                    "codes": CODE.findall(subject), "notes": NOTE.findall(body), "details": DETAIL.findall(body)})
    return out


def unreleased(since: str | None) -> tuple[list[tuple[str, str]], list[str]]:
    notes, details = [], []
    legacy = CHANGELOG / "UNRELEASED.md"
    if legacy.exists():
        sections = split_sections(legacy.read_text(encoding="utf-8"))
        notes += [tuple(n.split(": ", 1)) for n in bullets(sections.get("Notes", ""))]
        details += bullets(sections.get("Detail", ""))
    for c in commits(since):
        for text in c["notes"]:
            parsed = parse_note(text)
            if parsed:
                notes.append(parsed)
        label = " ".join(f"[{code}]" for code in c["codes"]) or c["subject"]
        pr = f" (#{c['pr']})" if c["pr"] else ""
        if c["details"]:
            details += [f"{c['date']} · {label}{pr}: {d}" for d in c["details"]]
        else:
            details.append(f"{c['date']} · {c['subject']}")
    return notes, details


def split_sections(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", text, re.M | re.S)}


def bullets(text: str) -> list[str]:
    """Bullets, each joined with its indented continuation lines."""
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("- "):
            out.append(line[2:].strip())
        elif line.startswith(" ") and out and line.strip():
            out[-1] += " " + line.strip()
    return out


def render_file(version: str, day: str, notes, details) -> str:
    lines = [f"# {version} · {day}", "", "## Notes", ""]
    lines += [f"- {pillar}: {sentence}" for pillar, sentence in notes] or ["- (none)"]
    lines += ["", "## Detail", ""] + [f"- {d}" for d in details]
    return "\n".join(lines) + "\n"


def render_releases() -> str:
    pillars = _pillars()
    lines = ["# Release notes", "",
             "What changed in each version, in plain words. Generated from `ai/changelog/` by `python tools/release_notes.py`; "
             "do not edit by hand. The full detail for each version is in the same folder.", ""]
    files = sorted((p for p in CHANGELOG.glob("*.md") if re.match(r"\d", p.name)), key=lambda p: version_key(p.stem), reverse=True)
    for path in files:
        head = path.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ")
        notes = [n for n in bullets(split_sections(path.read_text(encoding="utf-8")).get("Notes", "")) if n != "(none)"]
        if not notes:
            continue
        lines += [f"## {head}", ""]
        by_pillar: dict[str, list[str]] = {}
        for note in notes:
            pillar, sentence = note.split(": ", 1)
            by_pillar.setdefault(pillar, []).append(sentence)
        for pillar in pillars:
            if pillar in by_pillar:
                lines += [f"**{pillars[pillar]}**", ""] + [f"- {s}" for s in by_pillar[pillar]] + [""]
    lines += ["Earlier versions, and the detail behind every version: [ai/changelog/](ai/changelog/)."]
    return "\n".join(lines).rstrip("\n") + "\n"


def cut(version: str, since: str | None, day: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+(b\d+)?", version):
        raise SystemExit(f"{version!r} is not a version like 1.5.5")
    target = CHANGELOG / f"{version}.md"
    if target.exists():
        raise SystemExit(f"{target.relative_to(ROOT)} exists: a released version is never rewritten")
    notes, details = unreleased(since)
    migrations = sorted(Path(p).name for p in git("diff", "--name-only", f"{since}..HEAD").split()
                        if p.startswith("lightning/database/migrations/") and p.endswith(".sql")) if since else []
    if migrations:
        details.append(f"{day} · Migrations: {', '.join(migrations)}")
    target.write_text(render_file(version, day, notes, details), encoding="utf-8")
    legacy = CHANGELOG / "UNRELEASED.md"
    if legacy.exists():
        legacy.unlink()
    RELEASES.write_text(render_releases(), encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)} ({len(notes)} notes, {len(details)} detail lines) and RELEASES.md")


def check_pr(base: str) -> int:
    notes, details, problems = [], [], []
    for c in commits(base, first_parent=False):
        notes += c["notes"]
        details += c["details"]
    if not notes:
        problems.append("no commit has a `Release-note:` trailer (`Release-note: none` is allowed)")
    if not details:
        problems.append("no commit has a `Detail:` trailer (what changed, where and why, in one line)")
    for text in notes:
        try:
            parse_note(text)
        except ValueError as error:
            problems.append(str(error))
    print("\n".join(problems) or "release trailers fine")
    return 1 if problems else 0


def main() -> int:
    args = sys.argv[1:]
    since = args[args.index("--from") + 1] if "--from" in args else latest_tag()
    if args[:1] == ["recent"]:
        notes, details = unreleased(since)
        print(f"Unreleased since {since or 'the first commit'}:\n")
        print("Notes\n" + ("\n".join(f"  {p}: {s}" for p, s in notes) or "  (none yet)"))
        print("\nDetail\n" + ("\n".join(f"  {d}" for d in details) or "  (none yet)"))
        return 0
    if args[:1] == ["cut"]:
        if since is None:
            raise SystemExit("no tag v*: pass --from <commit of the last release>")
        cut(args[1], since, args[args.index("--date") + 1] if "--date" in args else date.today().isoformat())
        return 0
    if args[:1] == ["check-pr"]:
        return check_pr(args[1])
    text = render_releases()
    if "--check" in args:
        stale = not RELEASES.exists() or RELEASES.read_text(encoding="utf-8") != text
        print("RELEASES.md is out of date: run python tools/release_notes.py" if stale else "RELEASES.md fine")
        return 1 if stale else 0
    RELEASES.write_text(text, encoding="utf-8")
    print("wrote RELEASES.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
