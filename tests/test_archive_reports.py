"""tools/archive.py moves finished reports out of reports/ without breaking a link (IT-1M)."""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROWS = (
    "| old | [Old audit](2026-09-01-old/report.md) | 2026-09-01 | audit | none |\n"
    "| open | [Open audit](2026-09-02-open/report.md) | 2026-09-02 | audit | 3A |\n"
    "| ref | [Reference](2026-09-03-ref/report.md) | 2026-09-03 | reference | none |\n"
    "| new | [New audit](2026-10-30-new/report.md) | 2026-10-30 | audit | none |\n"
)


def _repo(tmp_path):
    for name in ("docs", "feedback", "templates", "guideline", "issues"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("# Index")
    (tmp_path / "ai").mkdir()
    (tmp_path / "ai" / "INDEX.md").write_text("# Map")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "README.md").write_text(
        "# Reports\n\n| ID | Report | Date | Kind | Open follow-ups |\n| --- | --- | --- | --- | --- |\n" + ROWS)
    for folder in ("2026-09-01-old", "2026-09-02-open", "2026-09-03-ref", "2026-10-30-new"):
        (tmp_path / "reports" / folder).mkdir()
        (tmp_path / "reports" / folder / "report.md").write_text("# Report")
    old = tmp_path / "reports" / "2026-09-01-old"
    (old / "evidence").mkdir()
    (old / "evidence" / "shot.png").write_bytes(b"png")
    (old / "evidence" / "repro.py").write_text("print('ok')")
    (old / "report.md").write_text(
        "# Old\n![Screen](evidence/shot.png)\n[Script](evidence/repro.py)\n[Plan](../../issues/README.md)\n"
        "[Sibling](../2026-09-02-open/report.md)\n")
    (tmp_path / "issues" / "item.md").write_text("[Old](../reports/2026-09-01-old/report.md#verdict)\n")
    return tmp_path


def test_plan_names_only_old_closed_reports(tmp_path):
    archive = _tool("archive")
    verdicts = {rid: reason for _, rid, reason in archive.plan(_repo(tmp_path), date(2026, 11, 4), 30)}
    assert verdicts["old"] is None
    assert "3A" in verdicts["open"] and "reference" in verdicts["ref"] and "newer than 30" in verdicts["new"]


def test_report_with_a_linked_image_stays(tmp_path):
    archive = _tool("archive")
    root = _repo(tmp_path)
    (root / "issues" / "item.md").write_text("![Shot](../reports/2026-09-01-old/evidence/shot.png)\n")
    verdicts = {rid: reason for _, rid, reason in archive.plan(root, date(2026, 11, 4), 30)}
    assert "issues/item.md" in verdicts["old"]


def test_archive_moves_text_drops_images_and_keeps_every_link(tmp_path):
    archive, docs_check = _tool("archive"), _tool("docs_check")
    root = _repo(tmp_path)
    archive.archive(root, "2026-09-01-old")
    moved = root / "ai" / "archive" / "reports" / "2026-09-01-old"
    assert not (root / "reports" / "2026-09-01-old").exists()
    assert not (moved / "evidence" / "shot.png").exists() and (moved / "evidence" / "repro.py").exists()
    text = (moved / "report.md").read_text()
    assert "Screen (image kept in git history)" in text and "../../../issues/README.md" in text
    assert "../../../reports/2026-09-02-open/report.md" in text
    assert "../ai/archive/reports/2026-09-01-old/report.md#verdict" in (root / "issues" / "item.md").read_text()
    assert "2026-09-01-old" not in (root / "reports" / "README.md").read_text()
    assert "(2026-09-01-old/report.md)" in (moved.parent / "README.md").read_text()
    assert docs_check.check(root) == []


def test_docs_check_flags_an_unregistered_archived_report(tmp_path):
    archive, docs_check = _tool("archive"), _tool("docs_check")
    root = _repo(tmp_path)
    archive.archive(root, "2026-09-01-old")
    (root / "ai" / "archive" / "reports" / "README.md").write_text("# Archived reports\n")
    assert any("absent from the archive catalogue" in error for error in docs_check.check(root))
