"""Move finished reports out of issues/<big picture>/ so the plan holds only live ones (IT-1M).

    python tools/archive.py                 # dry run: what would move, and why the rest stays
    python tools/archive.py --write         # do it
    python tools/archive.py --days 30       # minimum age of a report, in days (default 30)
    python tools/archive.py --issues        # dry run: milestones in issues/ with no open item
    python tools/archive.py --issues --write

A report moves to ai/archive/reports/<folder>/report.md when its catalogue row in issues/REPORTS.md has no open
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
HOMES = ("docs", "ai", "feedback", "templates", "guideline", "issues", "skills", "theme-kit")
ROW = re.compile(r"^\| ([a-z0-9.-]+) \| \[(.*)\]\((?:[^/)]+/)?([^/)]+)/report\.md\) \| (\d{4}-\d\d-\d\d) \| (\w+) \| (.*) \|$", re.M)
LINK = re.compile(r"(!?\[[^\]]*\]\()([^)]+)(\))")
ISSUES_ARCHIVE = Path("ai") / "archive" / "issues"
ISSUES_HEAD = (
    "# Archived milestones\n\n"
    "Milestones from [the plan](../../../issues/INDEX.md) whose items are all finished, moved here by\n"
    "`python tools/archive.py --issues --write`. Each folder keeps its README: the goal, the done-when line and every\n"
    "finished code. Those codes and the milestone's number stay reserved; they are never reused.\n\n"
    "| Milestone | Title | Finished codes |\n| --- | --- | --- |\n"
)
ARCHIVE_HEAD = (
    "# Archived reports\n\n"
    "Reports whose follow-ups are all finished, moved here by `python tools/archive.py`. The text and verdict are kept;\n"
    "evidence images are in git history. Active reports: [the catalogue](../../../issues/REPORTS.md).\n\n"
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


def report_folder(root: Path, folder: str) -> Path:
    """Where a report lives now: issues/<big picture>/<folder>."""
    found = sorted((root / "issues").glob(f"*/{folder}"))
    if not found:
        raise FileNotFoundError(f"no report folder {folder} under issues/")
    return found[0]


def plan(root: Path, today: date, days: int) -> list[tuple[str, str, str | None]]:
    """(folder, id, reason it stays or None when it moves) for every catalogued report."""
    text = (root / "issues" / "REPORTS.md").read_text(encoding="utf-8")
    result = []
    for rid, _title, folder, when, kind, follow in ROW.findall(text):
        reason = None
        if follow != "none":
            reason = f"open follow-ups: {follow}"
        elif kind == "reference":
            reason = "a reference is kept to be read"
        elif today - date.fromisoformat(when) < timedelta(days=days):
            reason = f"newer than {days} days (reviewed {when})"
        elif (links := outside_image_links(root, report_folder(root, folder))):
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
        if not resolved.exists() and parts[:1] == ("issues",) and len(parts) > 3 and re.match(r"r\d+-", parts[2]):
            resolved = (root / ARCHIVE).resolve().joinpath(*parts[2:])  # a report archived earlier
        return match.group(1) + os.path.relpath(resolved, target.resolve()).replace(os.sep, "/") + anchor + match.group(3)

    return LINK.sub(fix, text)


def _plain(match) -> str:
    return match.group(1).lstrip("!")[1:-2] + " (image kept in git history)"


def archive(root: Path, folder: str) -> None:
    source, target = report_folder(root, folder), root / ARCHIVE / folder
    target.mkdir(parents=True)
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if item.is_dir() or item.suffix.lower() in IMAGES:
            continue
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target / relative)
    report = target / "report.md"
    report.write_text(_relocate(root, report.read_text(encoding="utf-8"), source, target), encoding="utf-8")
    catalogue = root / "issues" / "REPORTS.md"
    text = catalogue.read_text(encoding="utf-8")
    row = next(m for m in ROW.finditer(text) if m.group(3) == folder)
    catalogue.write_text(text.replace(row.group(0) + "\n", ""), encoding="utf-8")
    _rewrite_links(root, source.resolve(), target.resolve())
    shutil.rmtree(source)
    index = root / ARCHIVE / "README.md"
    body = index.read_text(encoding="utf-8") if index.exists() else ARCHIVE_HEAD
    rid, title, _, when, kind, _ = row.groups()
    index.write_text(body.rstrip("\n") + f"\n| {rid} | [{title}]({folder}/report.md) | {when} | {kind} |\n", encoding="utf-8")


def finished_milestones(root: Path) -> list[Path]:
    """Milestone folders whose README is all that is left: every item is finished and deleted."""
    return [d for d in sorted((root / "issues").iterdir(), key=lambda p: p.name)
            if d.is_dir() and re.match(r"\d+-", d.name) and [f.name for f in d.glob("*.md")] == ["README.md"]
            and not any(p.is_dir() for p in d.iterdir())]


def archive_milestone(root: Path, folder: Path) -> None:
    """Move the milestone to ai/archive/issues/ and list it in that folder's README; relative links keep working."""
    target = root / ISSUES_ARCHIVE / folder.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(folder), str(target))
    readme = target / "README.md"
    text = readme.read_text(encoding="utf-8")
    title = re.search(r"^title: (.+)$", text, re.M)
    done = re.search(r"^done: (.+)$", text, re.M)
    index = root / ISSUES_ARCHIVE / "README.md"
    body = index.read_text(encoding="utf-8") if index.exists() else ISSUES_HEAD
    number = folder.name.split("-")[0]
    index.write_text(body.rstrip("\n") + f"\n| {number} | [{title.group(1) if title else folder.name}]({folder.name}/README.md) | "
                     f"{done.group(1) if done else 'none'} |\n", encoding="utf-8")
    _rewrite_folder_links(root, folder.resolve(), target.resolve())


def _rewrite_folder_links(root: Path, old: Path, new: Path) -> None:
    for path in documents(root):
        if new in path.resolve().parents:
            continue
        text = path.read_text(encoding="utf-8")

        def fix(match):
            target = _target(path, match.group(2))
            if target is None or (old != target and old not in target.parents):
                return match.group(0)
            anchor = "#" + match.group(2).split("#", 1)[1] if "#" in match.group(2) else ""
            moved = new if old == target else new / target.relative_to(old)
            return match.group(1) + os.path.relpath(moved, path.parent.resolve()).replace(os.sep, "/") + anchor + match.group(3)

        updated = LINK.sub(fix, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="move the reports (default: dry run)")
    parser.add_argument("--days", type=int, default=30, help="minimum age of a report in days")
    parser.add_argument("--issues", action="store_true", help="archive finished milestones of issues/ instead of reports")
    args = parser.parse_args()
    if args.issues:
        done = finished_milestones(ROOT)
        for folder in done:
            print(("archive  " if args.write else "would archive  ") + folder.name)
            if args.write:
                archive_milestone(ROOT, folder)
        print(f"{len(done)} finished milestone(s)." + ("" if args.write else " Add --write to move them."))
        if args.write:
            print("Now run python tools/issues.py, python tools/status.py and python tools/docs_check.py.")
        return
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
