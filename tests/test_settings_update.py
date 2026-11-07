"""NF-9B4: Settings › Lightning version, every state, with the update machinery faked (nothing touches the network).

The controller's own flow (check, download, restart, refusals) runs for real with injected effects; the page tests
attach a controller to the app and read the block and its polling endpoint.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.desktop import update as up
from lightning.desktop.update_controller import UpdateController
from lightning.ui.web import create_app

FOUND = up.Available("2.0.4", 31_457_280, "Lightning-v2.0.4-Windows-x64.zip", "a" * 64, "https://x/zip")


def controller(tmp_path, **kw) -> UpdateController:
    sync = {"run_async": lambda work: work()}
    return UpdateController(tmp_path / "Lightning", tmp_path / "updates", **{**sync, "current": "2.0.3", **kw})


def drive_to_ready(ctl, tmp_path):
    ctl.check = lambda current: FOUND
    ctl.download = lambda found, folder, progress=None: (progress and progress(5, 10)) or tmp_path / "z.zip"
    ctl.stage = lambda zip_path, version: tmp_path / "staged"
    ctl.start_check()
    assert ctl.status()["state"] == "available" and ctl.status()["size_mb"] == 31
    ctl.start_download()
    assert ctl.status()["state"] == "ready"


def test_the_whole_flow_check_download_stage_then_helper_and_quit(tmp_path):
    spawned, events = [], []
    ctl = controller(tmp_path, spawn=spawned.append, quit=lambda: events.append("quit"),
                     lock_profile=lambda: events.append("lock"), writable=lambda p: True)
    drive_to_ready(ctl, tmp_path)
    ctl.restart()
    assert events == ["lock", "quit"]
    command = spawned[0]
    assert command[0].endswith("staged/Lightning.exe") and command[1] == "--finish-update"
    assert command[command.index("--install") + 1] == str(tmp_path / "Lightning")
    assert command[command.index("--from") + 1] == "2.0.3" and command[command.index("--old-pid") + 1].isdigit()


def test_nothing_happens_unless_a_button_is_pressed(tmp_path):
    ctl = controller(tmp_path, check=lambda **kw: pytest.fail("checked on its own"))
    assert ctl.status()["state"] == "idle"
    ctl.restart(), ctl.start_download()  # out of order: ignored
    assert ctl.status()["state"] == "idle"


def test_up_to_date_and_failures_are_plain(tmp_path):
    ctl = controller(tmp_path, check=lambda current: up.UpToDate())
    ctl.start_check()
    assert ctl.status()["state"] == "up_to_date"
    ctl.check = lambda current: up.Failed("Lightning could not reach GitHub. Check the internet connection.")
    ctl.start_check()
    assert ctl.status() | {} and ctl.status()["state"] == "failed" and "internet" in ctl.status()["reason"]
    ctl.check = lambda current: FOUND

    def boom(found, folder, progress=None):
        raise up.UpdateError("The download does not match the signed update, so it was discarded.")
    ctl.download = boom
    ctl.start_check(), ctl.start_download()
    assert ctl.status()["state"] == "failed" and "does not match" in ctl.status()["reason"]


def test_restart_refuses_for_a_lent_profile_a_move_or_a_locked_folder_and_locks_nothing(tmp_path):
    events = []
    lent = type("D", (), {"borrowed": lambda self: [type("B", (), {"name": "Mona", "profile_id": "p", "state": __import__("lightning.sync.state", fromlist=["x"]).BorrowerState.BORROWING})()]})()
    ctl = controller(tmp_path, devices=lent, lock_profile=lambda: events.append("lock"), spawn=events.append,
                     writable=lambda p: True)
    drive_to_ready(ctl, tmp_path)
    ctl.restart()
    assert ctl.status()["state"] == "refused_lend" and ctl.status()["names"] == ["Mona"] and events == []
    ctl.devices = type("D", (), {"borrowed": lambda self: []})()
    (tmp_path / "profiles" / "Home" / ".journal-move").mkdir(parents=True)
    (tmp_path / "profiles" / "Home" / ".journal-move" / "client.state").write_bytes(b"x")
    ctl.profiles_root = tmp_path / "profiles"
    ctl.restart()
    assert ctl.status()["state"] == "refused_move" and events == []
    (tmp_path / "profiles" / "Home" / ".journal-move" / "client.state").unlink()
    ctl.writable = lambda p: False
    ctl.restart()
    assert ctl.status()["state"] == "refused_folder" and events == []
    ctl.writable = lambda p: True  # the person fixed it (handed back, finished the move): the same button works
    ctl.quit = lambda: events.append("quit")
    ctl.restart()
    assert events[0] == "lock" and events[-1] == "quit"


def test_a_helper_that_cannot_start_leaves_a_plain_message_not_a_dead_app(tmp_path):
    def broken(command):
        raise OSError("no")
    ctl = controller(tmp_path, spawn=broken, writable=lambda p: True, quit=lambda: pytest.fail("quit"))
    drive_to_ready(ctl, tmp_path)
    ctl.restart()
    assert ctl.status()["state"] == "failed"


def test_the_notice_after_an_update_or_a_failed_one_shows_once(tmp_path):
    ctl = controller(tmp_path, after_update="2.0.3", current="2.0.4")
    assert ctl.take_notice() == {"kind": "updated", "version": "2.0.4"} and ctl.take_notice() is None
    ctl = controller(tmp_path, update_failed="2.0.4")
    assert ctl.take_notice() == {"kind": "failed", "version": "2.0.4", "current": "2.0.3"}


def test_the_new_app_marks_ok_when_its_chooser_loads_only_after_an_update(tmp_path):
    controller(tmp_path).chooser_loaded()
    assert not (tmp_path / "updates").exists()
    controller(tmp_path, after_update="2.0.3", current="2.0.4").chooser_loaded()
    assert (tmp_path / "updates" / "ok-2.0.4").exists()


# ------------------------------------------------------------------------------ the page

@pytest.fixture(scope="module")
def ledger(tmp_path_factory):
    c = build(tmp_path_factory.mktemp("upd") / "t.db")
    yield c
    c.db.close()


def page(ledger, ctl=None, locale="en", path="/settings"):
    app = create_app(ledger)
    app.state.updates = ctl
    client = TestClient(app)
    assert client.post("/settings/locale", data={"locale": locale}, follow_redirects=False).status_code == 303
    return client, client.get(path)


def block(html: str) -> str:
    return re.search(r'<div class="settings-row" id="lightning-version".*?</form>\s*</div>', html, re.S).group(0)


def test_without_an_updater_the_block_shows_the_version_and_the_download_page(ledger):
    _, response = page(ledger)
    text = block(response.text)
    assert 'data-update-state="unavailable"' in text and "Download page" in text and "Check for updates" not in text


@pytest.mark.parametrize("state, extra, shows, button", [
    ("idle", {}, "Version 2.0.3", "Check for updates"),
    ("up_to_date", {}, "You have the newest version.", "Check for updates"),
    ("available", {"version": "2.0.4", "size_mb": 31}, "Version 2.0.4 is ready · 31 MB", "Download"),
    ("working", {"phase": "downloading", "percent": 40, "version": "2.0.4"}, "Downloading… 40%", None),
    ("working", {"phase": "verifying", "percent": 100, "version": "2.0.4"}, "Checking it works on this PC…", None),
    ("ready", {"version": "2.0.4"}, "Your profiles stay as they are.", "Restart to update"),
    ("refused_lend", {"names": ["Mona"], "version": "2.0.4"}, "Hand Mona back to your phone first, then update.", "Restart to update"),
    ("refused_move", {"names": ["Home"], "version": "2.0.4"}, "Finish moving the home of Home first", "Restart to update"),
    ("refused_folder", {}, "Lightning can&#39;t update itself in this folder. Download the new version instead.", "Download page"),
    ("failed", {"reason": "The update file is damaged."}, "The update file is damaged.", "Download it yourself"),
])
def test_every_state_reads_plainly_with_the_right_button(ledger, tmp_path, state, extra, shows, button):
    ctl = controller(tmp_path)
    ctl._state = {"state": state, **extra}
    client, response = page(ledger, ctl)
    text = block(response.text)
    assert shows in text and f'data-update-state="{state}"' in text
    if button:
        assert button in text
    assert ("data-update-poll" in text) == (state in ("checking", "working"))
    status = client.get("/settings/update/status")
    assert status.status_code == 200 and f'data-update-state="{state}"' in status.text and "<html" not in status.text


def test_the_buttons_drive_the_controller_and_never_the_network_on_load(ledger, tmp_path):
    calls = []
    ctl = controller(tmp_path, check=lambda current: calls.append("check") or up.UpToDate())
    client, _ = page(ledger, ctl)
    assert calls == []  # opening Settings checks nothing
    assert client.post("/settings/update/check", follow_redirects=False).status_code == 303 and calls == ["check"]
    assert 'data-update-state="up_to_date"' in client.get("/settings").text
    assert client.post("/settings/update/bogus", follow_redirects=False).status_code == 303 and calls == ["check"]


def test_the_one_time_notices(ledger, tmp_path):
    ctl = controller(tmp_path, update_failed="2.0.4")
    _, response = page(ledger, ctl)
    assert "The update to 2.0.4 didn&#39;t start, so you&#39;re back on 2.0.3." in response.text and "/current-status.html" in response.text
    ctl = controller(tmp_path, after_update="2.0.3", current="2.0.4")
    _, response = page(ledger, ctl)
    assert "Updated to 2.0.4." in block(response.text)


def test_arabic_shows_no_english_in_any_state(ledger, tmp_path):
    from test_arabic_no_english import _english
    for state, extra in [("idle", {}), ("up_to_date", {}), ("available", {"version": "2.0.4", "size_mb": 31}),
                         ("working", {"phase": "downloading", "percent": 40}), ("working", {"phase": "verifying"}),
                         ("ready", {}), ("refused_lend", {"names": ["Mona"]}), ("refused_move", {"names": ["Home"]}),
                         ("refused_folder", {}), ("failed", {"reason": "The update file is damaged."})]:
        ctl = controller(tmp_path)
        ctl._state = {"state": state, **extra}
        _, response = page(ledger, ctl, locale="ar")
        assert not _english(block(response.text), {"Mona", "Home"}), state
    _, response = page(ledger, None, locale="ar")
    assert not _english(block(response.text), set())
    for reason in re.findall(r'(?:UpdateError|Failed)\(\s*"([^"]+)"', Path(up.__file__).read_text(encoding="utf-8")):
        if "{" not in reason:
            from lightning.ui.i18n import translate
            assert translate(reason, "ar") != reason, reason
