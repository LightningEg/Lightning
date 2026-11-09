"""The Android shell (BT-2F): outside links and Back are wired, without a device.

The Java cannot run here, so these tests read it: each handler the WebView needs is present and keeps the locks
of task 04c (only this phone's server is loaded, no file or content access).
"""
from pathlib import Path

JAVA = Path(__file__).resolve().parents[1] / 'android/app/src/main/java/org/lightning/app'
MAIN = (JAVA / 'MainActivity.java').read_text()


def test_outside_links_open_in_the_browser_over_https_only():
    assert 'Intent.ACTION_VIEW' in MAIN and '"https".equals(uri.getScheme())' in MAIN
    assert 'getUserInfo() == null' in MAIN


def test_back_goes_to_overview_before_leaving():
    back = MAIN[MAIN.index('private void goBack'):]
    assert back.index('canGoBack') < back.index('"/".equals') < back.index('moveTaskToBack')


def test_back_uses_the_predictive_back_callback_from_api_33():
    """NF-11B1: target 36 means onBackPressed is never called on API 33+; the callback carries the same steps."""
    manifest = (JAVA.parents[3] / 'AndroidManifest.xml').read_text()
    assert 'android:enableOnBackInvokedCallback="true"' in manifest
    assert 'registerOnBackInvokedCallback' in MAIN and 'this::goBack' in MAIN
    pressed = MAIN[MAIN.index('public void onBackPressed'):]
    assert pressed.index('goBack();') < pressed.index('}')


def test_probe_screen_is_debug_only():
    main = JAVA.parents[3]
    assert 'ProbeActivity' not in (main / 'AndroidManifest.xml').read_text().split('-->')[-1]
    assert not (JAVA / 'ProbeActivity.java').exists()
    assert (main.parent / 'debug/java/org/lightning/app/ProbeActivity.java').exists()
    assert '.ProbeActivity' in (main.parent / 'debug/AndroidManifest.xml').read_text()


class _Recents:
    def __init__(self):
        self.on = True

    def hidden(self):
        return self.on

    def set_hidden(self, hide):
        self.on = hide


def test_settings_offers_hide_in_recent_apps_on_by_default(tmp_path):
    """NF-11B6: This phone has a "Hide in recent apps" switch, on by default, that the phone keeps by itself."""
    import re
    from fastapi.testclient import TestClient
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Credentials
    from test_profile_app import create
    recents = _Recents()
    cfg = Credentials("http://127.0.0.1:9852")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True, recents=recents)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as phone:
        phone.get("/__launch", params={"code": cfg.launch_code})
        create(phone)
        page = phone.get("/settings").text
        assert 'action="/profiles/recents"' in page and "Hide in recent apps" in page
        assert re.search(r'id="recents-hidden"[^>]*checked', page)
        csrf = re.search(r'action="/profiles/recents".*?name="csrf" value="([^"]+)"', page, re.S).group(1)
        phone.post("/profiles/recents", data={"csrf": csrf, "on": "0"})
        assert recents.on is False
        assert not re.search(r'id="recents-hidden"[^>]*checked', phone.get("/settings").text)
        phone.post("/profiles/recents", content=f"csrf={csrf}&on=0&on=1",  # the hidden 0, then the ticked box
                   headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert recents.on is True


def test_recents_are_blank_and_notifications_are_asked_in_context():
    bridge = (JAVA / 'RecentsBridge.java').read_text()
    assert 'setRecentsScreenshotEnabled(!hide)' in bridge and 'FLAG_SECURE' in bridge
    assert 'getBoolean(KEY, true)' in bridge  # on by default
    assert 'RecentsBridge.apply(this)' in MAIN
    create = MAIN[MAIN.index('public void onCreate'):MAIN.index('private void show(')]
    assert 'POST_NOTIFICATIONS' not in create  # never at first start
    assert 'if (result.enabled) runOnUiThread(this::askForNotifications)' in MAIN
