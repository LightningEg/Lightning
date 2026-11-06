"""BT-2AI3: after each day's first change a copy goes to the folder the person chose; the newest three stay."""
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.http import Credentials
from lightning.runtime.outside_copy import KEEP, OutsideCopy
from lightning.runtime.paths import discover_profiles
from lightning.runtime.profile_file import open_profile_file

from test_profile_app import PASSWORD, create, token


class FakeFolder:
    """Android's folder, in a directory: same rules as OutsideCopyBridge (replace a name, keep the newest three)."""

    def __init__(self, directory, chosen=True):
        self.directory, self.is_chosen, self.asked = Path(directory), chosen, 0

    def chosen(self):
        return self.is_chosen

    def choose(self):
        self.asked += 1
        return True

    def write(self, prefix, name, path):
        self.directory.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, self.directory / name)
        mine = sorted((p for p in self.directory.iterdir() if p.name.startswith(prefix)), reverse=True)
        for old in mine[KEEP:]:
            old.unlink()
        return True


def _phone(tmp_path, folder):
    cfg = Credentials("http://127.0.0.1:9876")
    outside = OutsideCopy(tmp_path / "state.json", folder, tmp_path / "scratch")
    app = profile_app(cfg, tmp_path / "Documents" / "Lightning", phone=True, files=_NoFiles(), outside=outside)
    browser = TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin})
    browser.get("/__launch", params={"code": cfg.launch_code})
    return browser, app, outside


class _NoFiles:
    def offer(self, name, media_type, data):
        return False


def test_the_first_change_each_day_writes_one_copy_that_opens_again(tmp_path):
    folder = FakeFolder(tmp_path / "outside")
    browser, app, outside = _phone(tmp_path, folder)
    with browser:
        create(browser)
        copies = list(folder.directory.glob("Home_*.lightning"))  # creating the book was the day's first change
        assert len(copies) == 1
        browser.get("/accounts/new")
        assert list(folder.directory.glob("Home_*.lightning")) == copies  # reading writes none
        profile_id = app.session.paths.profile.profile_id
        assert outside.last(profile_id) and not outside.due(profile_id)
        page = browser.get("/accounts/new")
        browser.post("/accounts/new", data={"__session": token(page.text, "__session"), "name": "Second",
                                            "account_type": "CASH", "currency": "EGP", "opening_balance": "0",
                                            "opening_date": "2026-09-30"})
        assert list(folder.directory.glob("Home_*.lightning")) == copies  # one a day
    reopened = open_profile_file(tmp_path / "fresh", copies[0], PASSWORD)  # the uninstall case: a fresh device
    assert [p.profile_id for p in discover_profiles(tmp_path / "fresh")] == [reopened.profile_id]


def test_only_the_newest_three_stay_and_no_folder_means_no_copy(tmp_path):
    folder = FakeFolder(tmp_path / "outside")
    for day in ("01", "02", "03", "04", "05"):
        source = tmp_path / f"Home_2026-11-{day}.lightning"
        source.write_bytes(b"x")
        folder.write("Home_", source.name, str(source))
    assert sorted(p.name for p in folder.directory.iterdir()) == [f"Home_2026-11-0{d}.lightning" for d in "345"]
    none = FakeFolder(tmp_path / "none", chosen=False)
    browser, app, outside = _phone(tmp_path / "b", none)
    with browser:
        create(browser)
        assert not outside.due(app.session.paths.profile.profile_id)
        assert not (tmp_path / "none").exists()


def test_settings_and_page_offer_the_folder_screen(tmp_path):
    folder = FakeFolder(tmp_path / "outside", chosen=False)
    browser, app, outside = _phone(tmp_path, folder)
    with browser:
        create(browser)
        assert "Copy outside the app" in browser.get("/settings").text
        page = browser.get("/profiles/outside-copy")
        assert "No copy outside the app" in page.text
        again = browser.post("/profiles/outside-copy", data={"csrf": token(page.text)})
        assert again.status_code == 200 and folder.asked == 1
