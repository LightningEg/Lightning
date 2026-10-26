"""Check documentation links and catalogues. Run from either repository root.

    python tools/docs_check.py
    python tools/docs_check.py --peer ../Lightning_website

Only public source documents are read; no network calls or private data access.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
HOMES = ("docs", "reports", "feedback", "templates", "guideline", "issues", "skills", "theme-kit")


def check(root: Path) -> list[str]:
    errors = []
    documents = set(root.glob("*.md"))
    for name in HOMES:
        documents.update((root / name).rglob("*.md"))
    for path in sorted(documents):
        # Examples inside fenced code are instructions, not navigable links.
        text = re.sub(r"(?ms)^```.*?^```[^\n]*", "", path.read_text(encoding="utf-8"))
        for link in re.findall(r"\]\(([^)]+)\)", text):
            link = link.strip().strip("<>")
            if re.match(r"[a-zA-Z][\w+.-]*:", link) or link.startswith("#"):
                continue
            target = unquote(link.split("#", 1)[0])
            if target and not (path.parent / target).exists():
                errors.append(f"{path.relative_to(root)}: missing link {target}")
    for name in ("docs", "reports", "feedback", "templates", "guideline"):
        if not (root / name / "README.md").is_file():
            errors.append(f"{name}/README.md: missing entry point")
    catalogue = root / "reports" / "README.md"
    registered = catalogue.read_text(encoding="utf-8") if catalogue.exists() else ""
    for report in sorted((root / "reports").rglob("report.md")):
        relative = report.relative_to(root / "reports").as_posix()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+/report\.md", relative):
            errors.append(f"reports/{relative}: expected YYYY-MM-DD-subject/report.md")
        if f"]({relative})" not in registered:
            errors.append(f"reports/{relative}: absent from catalogue")
    for path in (root / "reports").glob("*.md"):
        if path.name != "README.md":
            errors.append(f"{path.relative_to(root)}: report needs a dated subject folder")
    feedback_index = root / "feedback" / "README.md"
    registered = feedback_index.read_text(encoding="utf-8") if feedback_index.exists() else ""
    for record in (root / "feedback").glob("*.md"):
        if record.name == "README.md":
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md", record.name):
            errors.append(f"feedback/{record.name}: expected YYYY-MM-DD-subject.md")
        if f"]({record.name})" not in registered:
            errors.append(f"feedback/{record.name}: absent from catalogue")
    return errors


def mirrors(root: Path, peer: Path) -> list[str]:
    errors = []
    def files(base):
        return {p.name: p for p in (base / "guideline").iterdir() if p.suffix in (".md", ".html")}
    if not (peer / "guideline").is_dir():
        return [f"{peer}: missing guideline directory"]
    own, other = files(root), files(peer)
    for name in sorted(own.keys() | other.keys()):
        if name not in own or name not in other:
            errors.append(f"guideline/{name}: missing from one repository")
        elif own[name].read_bytes().replace(b"\r\n", b"\n") != other[name].read_bytes().replace(b"\r\n", b"\n"):
            errors.append(f"guideline/{name}: differs between repositories")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer", type=Path, help="also require all guideline Markdown/HTML files to match")
    args = parser.parse_args()
    errors = check(ROOT)
    if args.peer:
        errors.extend(mirrors(ROOT, args.peer.resolve()))
    print("\n".join(errors) if errors else "Documentation links and catalogues pass.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
