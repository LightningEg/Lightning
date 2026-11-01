"""Stay signed in on the phone (owner, 2026-11-01: "keep me logged in on the phone as long as I don't log out, not
every time I close it"). The data key is wrapped by a Keystore key that needs no fingerprint (StayBridge.java, a
fake here): opening the app opens the profile, idling never locks it, and Lock signs out for good."""
import time

from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials
from lightning.security.biometric import FingerprintUnlock, Outcome

from test_biometric_unlock import FakeBridge, lock
from test_profile_app import PASSWORD, create, token


def phone(tmp_path, bridge, *, phone=True, port=9881):
    cfg = Credentials(f"http://127.0.0.1:{port}")
    stay = FingerprintUnlock(tmp_path / "app" / "stay", bridge)
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=phone, stay=stay)
    browser = TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin})
    return browser, app, cfg, stay


def launch(browser, cfg):
    return browser.get("/__launch", params={"code": cfg.launch_code})


def unlock(browser, db, *, stay=True):
    page = browser.get("/profiles/unlock", params={"db": db})
    data = {"csrf": token(page.text), "db": db, "password": PASSWORD}
    if stay:
        data["stay"] = "yes"
    return browser.post("/profiles/unlock", data=data)


def signed_in(tmp_path, bridge, *, stay=True):
    """A profile made, locked, then unlocked with "Stay signed in" as given. Returns its database path."""
    browser, app, cfg, kept = phone(tmp_path, bridge)
    with browser:
        launch(browser, cfg)
        create(browser)
        db = str(app.session.paths.db_path)
        lock(browser)
        page = browser.get("/profiles/unlock", params={"db": db})
        assert ("Stay signed in on this phone" in page.text) is True
        assert unlock(browser, db, stay=stay).status_code == 200 and app.session.container is not None
        profile_id = app.session.paths.profile.profile_id
    # Leaving the block stops the app without Lock, as Android ends the process when the app is closed.
    return db, profile_id, kept


def test_closing_the_app_keeps_the_profile_signed_in(tmp_path):
    bridge = FakeBridge()
    _, profile_id, kept = signed_in(tmp_path, bridge)
    assert kept.enabled(profile_id) and bridge.prompts == 1  # wrapped once
    browser, app, cfg, _ = phone(tmp_path, bridge, port=9882)
    with browser:
        response = launch(browser, cfg)  # the launch link goes to /profiles, which opens the kept profile
        assert app.session.container is not None and response.url.path == "/"
        assert bridge.prompts == 2  # opened once by the bridge, no password typed


def test_lock_signs_out_for_good(tmp_path):
    bridge = FakeBridge()
    db, profile_id, kept = signed_in(tmp_path, bridge)
    browser, app, cfg, _ = phone(tmp_path, bridge, port=9883)
    with browser:
        launch(browser, cfg)
        assert app.session.container is not None
        lock(browser)
        assert not kept.enabled(profile_id) and profile_id in bridge.deleted
    browser, app, cfg, _ = phone(tmp_path, bridge, port=9884)
    with browser:
        launch(browser, cfg)
        assert app.session.container is None  # the password again


def test_unticked_keeps_nothing(tmp_path):
    bridge = FakeBridge()
    _, profile_id, kept = signed_in(tmp_path, bridge, stay=False)
    assert not kept.enabled(profile_id)


def test_a_locked_phone_shows_the_password_screen_and_keeps_the_slot(tmp_path):
    bridge = FakeBridge()
    _, profile_id, kept = signed_in(tmp_path, bridge)
    bridge.script = [Outcome.UNAVAILABLE]  # Android refuses the key while the phone is locked
    browser, app, cfg, _ = phone(tmp_path, bridge, port=9885)
    with browser:
        launch(browser, cfg)
        assert app.session.container is None and kept.enabled(profile_id)


def test_a_kept_profile_never_locks_for_idling(tmp_path):
    bridge = FakeBridge()
    signed_in(tmp_path, bridge)
    browser, app, cfg, _ = phone(tmp_path, bridge, port=9886)
    with browser:
        launch(browser, cfg)
        app.session.idle_seconds = 0
        time.sleep(1.6)
        assert app.session.container is not None
        lock(browser)
        db = next(p for p in (tmp_path / "docs").rglob("*.db") if "backup" not in str(p))
        unlock(browser, str(db), stay=False)
        app.session.idle_seconds = 0
        time.sleep(1.6)
        assert app.session.container is None  # not kept: the idle lock as before


def test_never_offered_on_a_pc(tmp_path):
    bridge = FakeBridge()
    browser, app, cfg, kept = phone(tmp_path, bridge, phone=False, port=9887)
    with browser:
        launch(browser, cfg)
        create(browser)
        db = str(app.session.paths.db_path)
        lock(browser)
        assert "Stay signed in" not in browser.get("/profiles/unlock", params={"db": db}).text
        unlock(browser, db)
        assert not kept.enabled(app.session.paths.profile.profile_id)
