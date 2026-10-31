"""The changelog is one file per version under ai/changelog/, and RELEASES.md is generated from them."""

import re
from pathlib import Path

import lightning

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "ai" / "changelog"


def test_current_version_has_its_notes():
    path = CHANGELOG / f"{lightning.__version__}.md"
    assert path.exists(), f"{path.relative_to(ROOT)} is missing: python tools/release_notes.py cut {lightning.__version__}"
    assert re.match(rf"# {re.escape(lightning.__version__)} · \d{{4}}-\d{{2}}-\d{{2}}", path.read_text(encoding="utf-8"))


def test_every_version_file_has_notes_and_detail_in_order():
    for path in CHANGELOG.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert re.findall(r"^## (.+)$", text, re.M) == ["Notes", "Detail"], f"{path.name}: sections must be Notes then Detail"
        if path.name != "UNRELEASED.md":
            assert re.fullmatch(r"\d+\.\d+\.\d+(b\d+)?", path.stem), f"{path.name} is not a version"
            assert re.match(rf"# {re.escape(path.stem)} · \d{{4}}-\d{{2}}-\d{{2}}", text), f"{path.name}: heading must be '# version · date'"


def test_every_released_migration_is_recorded():
    """Migrations are recorded when a version is cut; ones newer than anything recorded are still unreleased."""
    text = "".join(p.read_text(encoding="utf-8") for p in [*CHANGELOG.glob("*.md"), *(ROOT / "ai" / "archive").glob("*.md")])
    names = sorted(sql.name for sql in (ROOT / "lightning" / "database" / "migrations").glob("*.sql"))
    recorded = [n for n in names if n in text]
    assert recorded, "no migration is recorded in the changelog"
    missing = [n for n in names if n not in text and n < recorded[-1]]
    assert not missing, f"released migrations not recorded in ai/changelog/: {missing}"


def test_the_archive_holds_only_released_versions_and_is_linked():
    archive = (ROOT / "ai" / "archive" / "CHANGELOG-0.5-and-older.md").read_text(encoding="utf-8")
    assert "CHANGELOG-0.5-and-older.md" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+)$", archive, re.M)
    assert headings, "the archive has no versions"
    for heading in headings:
        assert re.match(r"\[\d+\.\d+\.\d+[^\]]*\] — \d{4}-\d{2}-\d{2}", heading), f"archive heading is not a released version: {heading}"


def test_the_readable_release_page_is_up_to_date():
    from tools import release_notes
    assert (ROOT / "RELEASES.md").read_text(encoding="utf-8") == release_notes.render_releases(), (
        "RELEASES.md is out of date: python tools/release_notes.py")
