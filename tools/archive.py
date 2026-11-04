"""Move finished reports out of reports/ so the working folder holds only live ones (IT-1M).

    python tools/archive.py                 # dry run: what would move, and why the rest stays
    python tools/archive.py --write         # do it
    python tools/archive.py --days 30       # minimum age of a report, in days (default 30)

A report moves to ai/archive/reports/<folder>/report.md when its catalogue row in reports/README.md has no open
follow-ups, it is not a reference, it is at least --days old, and nothing outside the report links to its images.
The text, verdict and non-image evidence stay; evidence images are deleted (git history keeps them) and the report's
own links to them become plain text. The catalogue row moves to ai/archive/reports/README.md and every relative
Markdown link to the report is rewritten, so tools/docs_check.py still passes.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("ai") / "archive" / "reports"
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
HOMES = ("docs", "ai", "reports", "feedback", "templates", "guideline", "issues", "skills", "theme-kit")
ROW = re.compile(r"^\| ([a-z0-9.-]+) \| \[(.*)\]\(([^/)]+)/report\.md\) \| (\d{4}-\d\d-\d\d) \| (\w+) \| (.*) \|$", re.M)
LINK = re.compile(r"(!?\[[^\]]*\]\()([^)]+)(\))")
ARCHIVE_HEAD = (
    "# Archived reports\n\n"
    "Reports whose follow-ups are all finished, moved here by `python tools/archive.py`. The text and verdict are kept;\n"
    "evidence images are in git history. Active reports: [reports](../../../reports/README.md).\n\n"
    "| Historical ID | Report | Review date | Kind |\n| --- | --- | --- | --- |\n"
)


def documents(root: Path) -> list[Path]:
    found = set(root.glob("*.md"))
    for name in HOMES:
        found.update((root / name).rglob("*.md"))
    return sorted(found)


def _target(path: Path, link: str) -> Path | None:
    link = link.strip().strip("<>")
    if re.match(r"[a-zA-Z][\w+.-]*:", link) or link.startswith("#"):
        return None
    target = unquote(link.split("#", 1)[0])
    return (path.parent / target).resolve() if target else None


def outside_image_links(root: Path, folder: Path) -> list[str]:
    """Documents outside the report folder that link to one of its images (those links would break)."""
    hits = []
    for path in documents(root):
        if folder.resolve() in path.resolve().parents:
            continue
        for _, link, _ in LINK.findall(path.read_text(encoding="utf-8")):
            target = _target(path, link)
            if target and folder.resolve() in target.parents and target.suffix.lower() in IMAGES:
                hits.append(str(path.relative_to(root)))
                break
    return hits


def plan(root: Path, today: date, days: int) -> list[tuple[str, str, str | None]]:
    """(folder, id, reason it stays or None when it moves) for every catalogued report."""
    text = (root / "reports" / "README.md").read_text(encoding="utf-8")
    result = []
    for rid, _title, folder, when, kind, follow in ROW.findall(text):
        reason = None
        if follow != "none":
            reason = f"open follow-ups: {follow}"
        elif kind == "reference":
            reason = "a reference is kept to be read"
        elif today - date.fromisoformat(when) < timedelta(days=days):
            reason = f"newer than {days} days (reviewed {when})"
        elif (links := outside_image_links(root, root / "reports" / folder)):
            reason = "images linked from " + ", ".join(links)
        result.append((folder, rid, reason))
    return result


def _rewrite_links(root: Path, old: Path, new: Path) -> None:
    for path in documents(root):
        if old in path.resolve().parents:
            continue
        text = path.read_text(encoding="utf-8")

        def fix(match):
            target = _target(path, match.group(2))
            if target is None or old not in target.parents or target.suffix.lower() in IMAGES:
                return match.group(0)
            anchor = "#" + match.group(2).split("#", 1)[1] if "#" in match.group(2) else ""
            moved = new / target.relative_to(old)
            return match.group(1) + os.path.relpath(moved, path.parent.resolve()).replace(os.sep, "/") + anchor + match.group(3)

        updated = LINK.sub(fix, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def _relocate(root: Path, text: str, source: Path, target: Path) -> str:
    """The report's own text at its new place: links out still reach their targets, links to dropped images become text."""
    def fix(match):
        link = match.group(2)
        if _target(source / "report.md", link) is None:
            return match.group(0)
        resolved = _target(source / "report.md", link)
        anchor = "#" + link.split("#", 1)[1] if "#" in link else ""
        if source.resolve() in resolved.parents or resolved == source.resolve():
            if (target / resolved.relative_to(source.resolve())).exists():
                return match.group(0)
            return _plain(match)
        parts = resolved.relative_to(root.resolve()).parts
        if not resolved.exists() and parts[:1] == ("reports",) and len(parts) > 1:
            resolved = (root / ARCHIVE).resolve().joinpath(*parts[1:])
        return match.group(1) + os.path.relpath(resolved, target.resolve()).replace(os.sep, "/") + anchor + match.group(3)

    return LINK.sub(fix, text)


def _plain(match) -> str:
    return match.group(1).lstrip("!")[1:-2] + " (image kept in git history)"


def archive(root: Path, folder: str) -> None:
    source, target = root / "reports" / folder, root / ARCHIVE / folder
    target.mkdir(parents=True)
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if item.is_dir() or item.suffix.lower() in IMAGES:
            continue
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target / relative)
    report = target / "report.md"
    report.write_text(_relocate(root, report.read_text(encoding="utf-8"), source, target), encoding="utf-8")
    catalogue = root / "reports" / "README.md"
    text = catalogue.read_text(encoding="utf-8")
    row = next(m for m in ROW.finditer(text) if m.group(3) == folder)
    catalogue.write_text(text.replace(row.group(0) + "\n", ""), encoding="utf-8")
    _rewrite_links(root, source.resolve(), target.resolve())
    shutil.rmtree(source)
    index = root / ARCHIVE / "README.md"
    body = index.read_text(encoding="utf-8") if index.exists() else ARCHIVE_HEAD
    rid, title, _, when, kind, _ = row.groups()
    index.write_text(body.rstrip("\n") + f"\n| {rid} | [{title}]({folder}/report.md) | {when} | {kind} |\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="move the reports (default: dry run)")
    parser.add_argument("--days", type=int, default=30, help="minimum age of a report in days")
    args = parser.parse_args()
    rows = plan(ROOT, date.today(), args.days)
    moving = [folder for folder, _, reason in rows if reason is None]
    for folder, rid, reason in rows:
        print(f"{'move' if reason is None else 'stay'}  {rid}" + (f"  ({reason})" if reason else ""))
    if args.write:
        for folder in moving:
            archive(ROOT, folder)
        print(f"Archived {len(moving)} report(s). Run python tools/status.py and python tools/docs_check.py.")
    else:
        print(f"Dry run: {len(moving)} of {len(rows)} would move. Add --write to do it.")


if __name__ == "__main__":
    main()
