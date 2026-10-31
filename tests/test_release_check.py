"""A prepared release has its notes in ai/changelog/<version>.md, with nothing left waiting in UNRELEASED.md."""
from tools import release_check


def test_prepared_release_notes_must_match_source_version(tmp_path, monkeypatch):
    monkeypatch.setattr(release_check, "ROOT", tmp_path)
    for name in ("LICENSE", "CONTRIBUTING.md"):
        (tmp_path / name).write_text("present")
    (tmp_path / "pyproject.toml").write_text('version = "1.5.0"\n')
    folder = tmp_path / "ai" / "changelog"
    folder.mkdir(parents=True)
    notes = folder / "1.5.0.md"
    notes.write_text("# 1.5.0 · 2026-10-26\n\n## Notes\n\n- feel: Prepared release.\n\n## Detail\n\n- x\n")
    assert release_check.files() == []
    notes.rename(folder / "1.4.4.md")
    assert release_check.files(), "Notes for an older release must not validate this release"
    (folder / "1.4.4.md").rename(notes)
    notes.write_text("# 1.5.0 · 2026-10-26\n\n## Notes\n\n## Detail\n\n- x\n")
    assert release_check.files(), "A version file without notes is insufficient"
    notes.write_text("# 1.5.0 · 2026-10-26\n\n## Notes\n\n- feel: Prepared release.\n\n## Detail\n\n- x\n")
    (folder / "UNRELEASED.md").write_text("waiting")
    assert release_check.files(), "Entries left in UNRELEASED.md must be cut into the release first"
