"""Release notes come from commit trailers: parsed, cut into a version file, rendered for people, checked on a pull request."""
import subprocess

import pytest

from tools import release_notes


def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@e", "PATH": subprocess.os.environ["PATH"], "HOME": str(path)})


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "ai" / "changelog").mkdir(parents=True)
    monkeypatch.setattr(release_notes, "ROOT", tmp_path)
    monkeypatch.setattr(release_notes, "CHANGELOG", tmp_path / "ai" / "changelog")
    monkeypatch.setattr(release_notes, "RELEASES", tmp_path / "RELEASES.md")
    (tmp_path / "a.txt").write_text("1")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "first")
    _git(tmp_path, "tag", "v1.0.0")
    return tmp_path


def _commit(repo, subject, body=""):
    (repo / "a.txt").write_text(subject)
    _git(repo, "commit", "-qam", subject + ("\n\n" + body if body else ""))


def test_a_note_is_a_pillar_and_a_sentence_or_none():
    assert release_notes.parse_note("own: Convert asks once.") == ("own", "Convert asks once.")
    assert release_notes.parse_note("none") is None
    for bad in ("Convert asks once.", "money: A sentence.", "own:"):
        with pytest.raises(ValueError):
            release_notes.parse_note(bad)


def test_versions_sort_newest_first_and_a_beta_sorts_below_its_release():
    names = ["1.5.2", "1.1.0b1", "1.10.0", "1.1.0", "1.5.4"]
    assert sorted(names, key=release_notes.version_key, reverse=True) == ["1.10.0", "1.5.4", "1.5.2", "1.1.0", "1.1.0b1"]


def test_cut_writes_the_version_file_and_the_readable_page(repo):
    _commit(repo, "[BT-5J] Ask once before saving a conversion (#206)",
            "Release-note: own: Converting EGP to dollars asks first.\nDetail: Convert refuses a rate 20% off the market.")
    _commit(repo, "Tidy tests (#207)", "Release-note: none\nDetail: Renamed a fixture.")
    release_notes.cut("1.0.1", "v1.0.0", "2026-11-01")
    text = (repo / "ai" / "changelog" / "1.0.1.md").read_text(encoding="utf-8")
    assert "- own: Converting EGP to dollars asks first." in text
    assert "[BT-5J] (#206): Convert refuses a rate 20% off the market." in text
    assert "Renamed a fixture" in text and text.count("- own:") == 1
    page = (repo / "RELEASES.md").read_text(encoding="utf-8")
    assert "## 1.0.1 · 2026-11-01" in page and "**Own**" in page and "Converting EGP" in page
    with pytest.raises(SystemExit):
        release_notes.cut("1.0.1", "v1.0.0", "2026-11-01")  # a released version is never rewritten


def test_cut_takes_in_entries_made_before_trailers_and_removes_them(repo):
    legacy = repo / "ai" / "changelog" / "UNRELEASED.md"
    legacy.write_text("# Unreleased\n\n## Notes\n\n- feel: Menus close on Escape.\n\n## Detail\n\n- 2026-10-30 · Claude: Menus.\n")
    release_notes.cut("1.0.1", "v1.0.0", "2026-11-01")
    assert not legacy.exists()
    text = (repo / "ai" / "changelog" / "1.0.1.md").read_text(encoding="utf-8")
    assert "- feel: Menus close on Escape." in text and "2026-10-30 · Claude: Menus." in text


def test_a_version_without_notes_stays_out_of_the_readable_page(repo):
    (repo / "ai" / "changelog" / "1.0.0.md").write_text("# 1.0.0 · 2026-10-01\n\n## Notes\n\n- (none)\n\n## Detail\n\n- x\n")
    assert "1.0.0" not in release_notes.render_releases().split("Earlier versions")[0]


def test_a_pull_request_needs_both_trailers(repo, capsys):
    _commit(repo, "Change", "Release-note: capture: Import is faster.")
    assert release_notes.check_pr("v1.0.0") == 1 and "Detail" in capsys.readouterr().out
    _commit(repo, "More", "Detail: Cached the header read.")
    assert release_notes.check_pr("v1.0.0") == 0
    _commit(repo, "Bad", "Release-note: Import is faster.\nDetail: x")
    assert release_notes.check_pr("v1.0.0") == 1


def test_a_pull_request_checked_out_as_a_merge_commit_is_still_read(repo):
    """CI checks out the merge of the PR into the base; the base is the merge's first parent."""
    _git(repo, "checkout", "-q", "-b", "pr")
    _commit(repo, "Change", "Release-note: capture: Import is faster.\nDetail: Cached the header read.")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "merge-ref")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge pr", "pr")
    assert release_notes.check_pr("v1.0.0") == 0
