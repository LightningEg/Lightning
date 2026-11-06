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
    "| r1 | [Old audit](r1-old/report.md) | 2026-09-01 | audit | none |\n"
    "| r2 | [Open audit](r2-open/report.md) | 2026-09-02 | audit | 3A |\n"
    "| r3 | [Reference](r3-ref/report.md) | 2026-09-03 | reference | none |\n"
    "| r4 | [New audit](r4-new/report.md) | 2026-10-30 | audit | none |\n"
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
    for folder in ("r1-old", "r2-open", "r3-ref", "r4-new"):
        (tmp_path / "reports" / folder).mkdir()
        (tmp_path / "reports" / folder / "report.md").write_text("# Report\n\nCode: " + folder.split("-")[0])
    old = tmp_path / "reports" / "r1-old"
    (old / "evidence").mkdir()
    (old / "evidence" / "shot.png").write_bytes(b"png")
    (old / "evidence" / "repro.py").write_text("print('ok')")
    (old / "report.md").write_text(
        "# Old\n\nCode: r1\n![Screen](evidence/shot.png)\n[Script](evidence/repro.py)\n[Plan](../../issues/README.md)\n"
        "[Sibling](../r2-open/report.md)\n")
    (tmp_path / "issues" / "item.md").write_text("[Old](../reports/r1-old/report.md#verdict)\n")
    return tmp_path


def test_plan_names_only_old_closed_reports(tmp_path):
    archive = _tool("archive")
    verdicts = {rid: reason for _, rid, reason in archive.plan(_repo(tmp_path), date(2026, 11, 4), 30)}
    assert verdicts["r1"] is None
    assert "3A" in verdicts["r2"] and "reference" in verdicts["r3"] and "newer than 30" in verdicts["r4"]


def test_report_with_a_linked_image_stays(tmp_path):
    archive = _tool("archive")
    root = _repo(tmp_path)
    (root / "issues" / "item.md").write_text("![Shot](../reports/r1-old/evidence/shot.png)\n")
    verdicts = {rid: reason for _, rid, reason in archive.plan(root, date(2026, 11, 4), 30)}
    assert "issues/item.md" in verdicts["r1"]


def test_archive_moves_text_drops_images_and_keeps_every_link(tmp_path):
    archive, docs_check = _tool("archive"), _tool("docs_check")
    root = _repo(tmp_path)
    archive.archive(root, "r1-old")
    moved = root / "ai" / "archive" / "reports" / "r1-old"
    assert not (root / "reports" / "r1-old").exists()
    assert not (moved / "evidence" / "shot.png").exists() and (moved / "evidence" / "repro.py").exists()
    text = (moved / "report.md").read_text()
    assert "Screen (image kept in git history)" in text and "../../../issues/README.md" in text
    assert "../../../reports/r2-open/report.md" in text
    assert "../ai/archive/reports/r1-old/report.md#verdict" in (root / "issues" / "item.md").read_text()
    assert "r1-old" not in (root / "reports" / "README.md").read_text()
    assert "(r1-old/report.md)" in (moved.parent / "README.md").read_text()
    assert docs_check.check(root) == []


def test_docs_check_flags_an_unregistered_archived_report(tmp_path):
    archive, docs_check = _tool("archive"), _tool("docs_check")
    root = _repo(tmp_path)
    archive.archive(root, "r1-old")
    (root / "ai" / "archive" / "reports" / "README.md").write_text("# Archived reports\n")
    assert any("absent from the archive catalogue" in error for error in docs_check.check(root))
