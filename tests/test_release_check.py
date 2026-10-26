"""A prepared release has its notes below the version, with Unreleased empty."""
from tools import release_check


def test_prepared_release_notes_must_match_source_version(tmp_path, monkeypatch):
    monkeypatch.setattr(release_check, "ROOT", tmp_path)
    for name in ("LICENSE", "CONTRIBUTING.md"):
        (tmp_path / name).write_text("present")
    (tmp_path / "pyproject.toml").write_text('version = "1.5.0"\n')
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [Unreleased]\n\n## [1.5.0] · 2026-10-26\n\n- 2026-10-26 · Prepared release.\n")
    assert release_check.files() == []
    changelog.write_text(changelog.read_text().replace("[1.5.0]", "[1.4.4]"))
    assert release_check.files(), "Notes for an older release must not validate this release"
    changelog.write_text("## [Unreleased]\n\n## [1.5.0]\n\n")
    assert release_check.files(), "An empty matching heading is insufficient"
