"""IT-2C3: "Choose a backup file…" restores a backup kept outside the profile (a USB stick) via a picker."""

from __future__ import annotations

import shutil

import pytest

from lightning.runtime import file_picker
from tests.test_profile_app import PASSWORD, create, start, token


@pytest.fixture(autouse=True)
def no_picker():
    file_picker.register(None)
    yield
    file_picker.register(None)


def _backup_outside(browser, app, tmp_path, marker):
    browser.portal.call(app.session.container.settings.set, "restore_ui_marker", marker)
    saved = browser.portal.call(app.session.container.backup_now)
    outside = tmp_path / "usb" / "my-backup.db"
    outside.parent.mkdir(exist_ok=True)
    shutil.copy2(saved, outside)
    saved.unlink()
    return outside


def test_without_a_picker_the_route_is_not_there(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        live = app.session.paths.db_path
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
        page = browser.get("/profiles/restore", params={"db": str(live)})
        assert "Choose a backup file" not in page.text
        assert browser.post("/profiles/restore/pick", data={"csrf": token(page.text), "db": str(live)}).status_code == 404


def test_a_backup_from_outside_the_profile_restores(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        live = app.session.paths.db_path
        outside = _backup_outside(browser, app, tmp_path, "saved version")
        browser.portal.call(app.session.container.settings.set, "restore_ui_marker", "newer version")
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
        file_picker.register(lambda: str(outside))
        page = browser.get("/profiles/restore", params={"db": str(live)})
        assert "Choose a backup file" in page.text
        before = outside.read_bytes()
        chosen = browser.post("/profiles/restore/pick", data={"csrf": token(page.text), "db": str(live)})
        assert chosen.status_code == 200 and "Replace this profile with the selected backup." in chosen.text
        copied = \
            list((live.parent / "backups").glob("*_picked.db"))
        assert len(copied) == 1 and outside.read_bytes() == before
        restored = browser.post("/profiles/restore", data={
            "csrf": token(chosen.text), "db": str(live), "backup": str(copied[0]), "password": PASSWORD, "confirm": "yes"})
        assert restored.status_code == 200 and "Backup restored" in restored.text, restored.text
        unlocked = browser.post("/profiles/unlock", data={"csrf": token(restored.text), "db": str(live), "password": PASSWORD})
        assert unlocked.status_code == 200
        assert browser.portal.call(app.session.container.settings.get, "restore_ui_marker") == "saved version"


def test_another_profiles_backup_is_refused_and_its_copy_removed(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser, name="Other")
        foreign = _backup_outside(browser, app, tmp_path, "other profile")
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
        create(browser, name="Home")
        live = app.session.paths.db_path
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
        file_picker.register(lambda: str(foreign))
        page = browser.get("/profiles/restore", params={"db": str(live)})
        chosen = browser.post("/profiles/restore/pick", data={"csrf": token(page.text), "db": str(live)})
        copied = list((live.parent / "backups").glob("*_picked.db"))
        assert len(copied) == 1
        refused = browser.post("/profiles/restore", data={
            "csrf": token(chosen.text), "db": str(live), "backup": str(copied[0]), "password": PASSWORD, "confirm": "yes"})
        assert refused.status_code == 400 and "uses another key" in refused.text
        assert not list((live.parent / "backups").glob("*_picked.db"))
        assert foreign.is_file()


def test_cancelling_the_dialog_changes_nothing(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        live = app.session.paths.db_path
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
        file_picker.register(lambda: None)
        page = browser.get("/profiles/restore", params={"db": str(live)})
        back = browser.post("/profiles/restore/pick", data={"csrf": token(page.text), "db": str(live)})
        assert back.status_code == 200 and not list((live.parent / "backups").glob("*_picked.db"))
