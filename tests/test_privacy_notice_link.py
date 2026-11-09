"""The app's privacy notice (NF-11B4): Settings opens the website's privacy notice at its App section, in the page's
language, in the system browser; the PC window lets exactly that page out. Google Play wants the policy inside the app."""
from fastapi.testclient import TestClient

from lightning.desktop.window import _store_link
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials
from lightning.ui.entitlements import outside_url

from test_profile_app import create, token


def test_the_notice_is_the_websites_app_section_in_each_language():
    assert outside_url("privacy") + "#app" == "https://lightningeg.com/privacy.html#app"
    assert outside_url("privacy", "ar") + "#app" == "https://lightningeg.com/ar/privacy.html#app"
    assert _store_link("https://lightningeg.com/privacy.html#app") and _store_link("https://lightningeg.com/ar/privacy.html#app")
    assert not _store_link("https://lightningeg.com/account.html")


def test_settings_has_a_privacy_row_on_the_phone_and_in_arabic(tmp_path):
    cfg = Credentials("http://127.0.0.1:9867")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        page = browser.get("/settings").text
        assert 'href="https://lightningeg.com/privacy.html#app" target="_blank"' in page
        browser.post("/settings/locale", data={"locale": "ar", "__session": token(page, "__session")})
        page = browser.get("/settings").text
        assert 'href="https://lightningeg.com/ar/privacy.html#app"' in page and "اقرا إشعار الخصوصية" in page
