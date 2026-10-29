"""CodeQL on Audit 9 (PR 190): redirects stay inside the app, and a posted path is a profile before anything reads beside it."""

import pytest

from lightning.ui.web import redirect


@pytest.mark.parametrize("url", ["https://evil.example/x", "//evil.example/x", "/\\evil.example", "evil.example", "", "/a\r\nSet-Cookie: x=1"])
def test_redirect_never_leaves_the_app(url):
    assert redirect(url).headers["location"] == "/"


def test_redirect_keeps_app_paths_and_the_message():
    assert redirect("/transactions/5", "Saved").headers["location"] == "/transactions/5?msg=Saved"
    assert redirect("/budget?month=2026-10", "Hi there").headers["location"] == "/budget?month=2026-10&msg=Hi%20there"


def test_a_posted_path_that_is_not_a_profile_is_not_probed(tmp_path, monkeypatch):
    from lightning.runtime import devices
    (tmp_path / "journal-native.json").write_text("{}")  # beside a path that is no profile
    seen = []
    monkeypatch.setattr(devices, "is_journal_profile", lambda folder: seen.append(folder) or False)
    manager = devices.Devices.__new__(devices.Devices)
    assert manager.role_for(str(tmp_path / "not-a-profile.db")) == "home"
    assert seen == [], "no marker lookup for a path that is not a profile"

