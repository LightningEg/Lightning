"""Privacy on screen (NF-11B6, r29 S6, S9): "Hide in recent apps" in Settings › This phone, on by default, and the
notification question asked when reminders are turned on, never at the first start.

The Java cannot run here, so its wiring is read; the switch is rendered and pressed through the phone app."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials

from test_profile_app import create, token

JAVA = Path(__file__).resolve().parents[1] / "android/app/src/main/java/org/lightning/app"
MAIN = (JAVA / "MainActivity.java").read_text()
SCREEN = (JAVA / "ScreenBridge.java").read_text()


class FakeScreen:
    def __init__(self):
        self.hide = True  # ScreenBridge's default

    def hidden(self):
        return self.hide

    def set_hidden(self, hide):
        self.hide = bool(hide)


@pytest.fixture(scope="module")
def phone(tmp_path_factory):
    folder = tmp_path_factory.mktemp("phone-screen")
    cfg = Credentials("http://127.0.0.1:9863")
    screen = FakeScreen()
    app = profile_app(cfg, folder / "docs", devices=Devices(folder / "app", port=0), phone=True, screen=screen)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        yield browser, screen


def _row(html):
    match = re.search(r'<form class="phone-row" method="post" action="/settings/phone/recents">.*?</form>', html, re.S)
    assert match, "the This phone section has no Hide in recent apps row"
    return match.group(0)


def test_the_switch_is_on_by_default_and_turns_off_and_on(phone):
    browser, screen = phone
    row = _row(browser.get("/settings").text)
    assert "Hide in recent apps" in row and "blank card" in row and 'name="hide" value="0"' in row
    page = browser.get("/settings").text
    browser.post("/settings/phone/recents", data={"hide": "0", "__session": token(page, "__session")})
    assert screen.hide is False
    row = _row(browser.get("/settings").text)
    assert "can show this screen" in row and 'name="hide" value="1"' in row
    page = browser.get("/settings").text
    browser.post("/settings/phone/recents", data={"hide": "1", "__session": token(page, "__session")})
    assert screen.hide is True


def test_a_pc_and_a_phone_without_the_bridge_show_no_switch(tmp_path):
    cfg = Credentials("http://127.0.0.1:9864")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        assert "/settings/phone/recents" not in browser.get("/settings").text


def test_recents_are_blank_from_the_first_frame():
    create_at = MAIN.index("public void onCreate")
    assert create_at < MAIN.index("ScreenBridge.apply(this)") < MAIN.index("setContentView(frame)")
    assert "getBoolean(KEY, true)" in SCREEN  # on by default
    assert "setRecentsScreenshotEnabled(!hide)" in SCREEN and "FLAG_SECURE" in SCREEN
    assert 'jclass("org.lightning.app.ScreenBridge")' in (
        JAVA.parents[3] / "python/lightning_android.py").read_text()


def test_notifications_are_asked_for_when_reminders_turn_on_not_at_first_start():
    start = MAIN[MAIN.index("public void onCreate"):MAIN.index("private void show(")]
    assert "POST_NOTIFICATIONS" not in start
    reminders = MAIN[MAIN.index("private void checkReminders"):]
    assert reminders.index("result.enabled") < reminders.index("askForNotifications")
    ask = MAIN[MAIN.index("private void askForNotifications"):]
    assert "requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}" in ask
