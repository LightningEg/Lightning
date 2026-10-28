"""The real app's request guard (runtime/http.py), the one-holder profile lock message, the phone template
choice and the window's refusal of new windows."""
import sys
import threading
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials, Guard
from lightning.runtime.session import ProfileError, ProfileSession
from lightning.ui.web import _phone_template

from test_profile_app import create, token

PASSWORD = "a correct long passphrase"


async def _inner(scope, receive, send):
    await PlainTextResponse("inside " + scope["path"])(scope, receive, send)


def guarded():
    cfg = Credentials("http://127.0.0.1:9871")
    return TestClient(Guard(_inner, cfg), base_url=cfg.origin, follow_redirects=False), cfg


def test_a_correct_launch_link_sets_the_cookie_and_only_requests_with_it_pass():
    browser, cfg = guarded()
    assert browser.get("/profiles").status_code == 403
    response = browser.get("/__launch", params={"code": cfg.launch_code})
    assert response.status_code == 303 and response.headers["location"] == "/profiles"
    assert response.cookies[cfg.cookie_name] == cfg.token
    assert "httponly" in response.headers["set-cookie"].lower()
    page = browser.get("/profiles")
    assert page.status_code == 200 and page.text == "inside /profiles"
    browser.cookies.clear()
    refused = browser.get("/profiles")
    assert refused.status_code == 403 and refused.text == "Forbidden"


def test_a_launch_link_works_once():
    browser, cfg = guarded()
    assert browser.get("/__launch", params={"code": cfg.launch_code}).status_code == 303
    again = browser.get("/__launch", params={"code": cfg.launch_code})
    assert again.status_code == 403 and again.text == "Launch link expired. Restart Lightning."


def test_an_expired_launch_link_is_refused_and_sets_no_cookie():
    browser, cfg = guarded()
    cfg.expires = 0
    response = browser.get("/__launch", params={"code": cfg.launch_code})
    assert response.status_code == 403 and response.text == "Launch link expired. Restart Lightning."
    assert cfg.cookie_name not in response.cookies and cfg.used is False


def test_a_launch_code_with_a_non_ascii_character_is_refused_without_an_error():
    browser, cfg = guarded()
    for code in ("é", cfg.launch_code[:-1] + "é"):
        response = browser.get("/__launch", params={"code": code})
        assert response.status_code == 403 and response.text == "Launch link expired. Restart Lightning."
    assert cfg.used is False
    assert browser.get("/__launch", params={"code": cfg.launch_code}).status_code == 303


def test_two_instances_get_different_cookie_names_and_one_cookie_does_not_open_the_other():
    first, second = Credentials("http://127.0.0.1:9871"), Credentials("http://127.0.0.1:9871")
    assert first.cookie_name != second.cookie_name and first.token != second.token
    browser = TestClient(Guard(_inner, second), base_url=second.origin, follow_redirects=False)
    browser.cookies.set(first.cookie_name, first.token)
    assert browser.get("/profiles").status_code == 403


def test_opening_a_profile_another_process_holds_says_so_and_the_holder_keeps_working(tmp_path):
    root = tmp_path / "Documents" / "Lightning"
    holder = ProfileSession(root)
    holder.prepare("Home", PASSWORD, PASSWORD, "What was the name of your first school?", "El Orman")
    holder.confirm(holder.pending.recovery)
    other = ProfileSession(root)
    with pytest.raises(ProfileError) as refused:
        other.unlock(str(holder.paths.db_path), PASSWORD)
    assert str(refused.value) == "This profile is open in another Lightning process. Close it there first."
    assert other.container is None and other.paths is None
    holder.container.settings.set("test_marker", "still mine")
    assert holder.container.settings.get("test_marker") == "still mine"
    holder.close()


def test_a_page_with_a_phone_screen_uses_it_and_any_other_page_keeps_its_own():
    templates = Path(__file__).resolve().parents[1] / "lightning/ui/templates"
    phone = {p.relative_to(templates / "phone").as_posix() for p in (templates / "phone").rglob("*.html")}
    assert {"dashboard/index.html", "accounts/list.html"} <= phone
    for name in phone - {"base.html"}:
        if (templates / name).exists():
            assert _phone_template(name) == f"phone/{name}"
    assert "settings/index.html" not in phone
    assert _phone_template("settings/index.html") == "settings/index.html"


def test_on_the_phone_the_overview_is_its_phone_screen_and_settings_is_the_pc_page_in_the_phone_frame(tmp_path):
    cfg = Credentials("http://127.0.0.1:9872")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        browser.post("/demo", data={"__session": token(browser.get("/").text, "__session")})
        overview, settings = browser.get("/").text, browser.get("/settings").text
    for html in (overview, settings):
        assert html.count('class="phone-tabbar"') == 1 and 'class="side"' not in html
    assert 'class="phone-section" aria-labelledby="position-heading"' in overview and "overview-section" not in overview
    assert "Your data</h2>" in settings and "Back up now" in settings


class _Event:
    def __init__(self, ready=True):
        self.handlers, self.ready = [], ready

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def wait(self, _timeout=None):
        return self.ready


class _NewWindowRequest:
    handled = False

    def set_Handled(self, value):
        self.handled = value


def test_the_window_refuses_a_new_window_and_leaves_the_app_where_it_is(monkeypatch):
    import importlib.metadata

    from lightning.desktop import window as module

    core = types.SimpleNamespace(NavigationStarting=_Event(), NewWindowRequested=_Event())
    init = _Event()
    loads, loaded_here = [], threading.Event()
    win = types.SimpleNamespace(
        native=types.SimpleNamespace(browser=types.SimpleNamespace(
            webview=types.SimpleNamespace(CoreWebView2InitializationCompleted=init))),
        events=types.SimpleNamespace(initialized=_Event(), before_show=_Event(), closed=_Event(),
                                     shown=_Event(), loaded=_Event()),
        load_url=lambda url: (loads.append(url), loaded_here.set()),
        get_current_url=lambda: loads[-1] if loads else "about:blank",
    )
    url, origin = "http://127.0.0.1:43123/__launch?code=x", "http://127.0.0.1:43123"
    requests = []

    def start(**_kwargs):
        for handler in win.events.before_show.handlers:
            handler()
        for handler in init.handlers:
            handler(types.SimpleNamespace(CoreWebView2=core), types.SimpleNamespace(IsSuccess=True))
        assert loaded_here.wait(5)
        for handler in win.events.loaded.handlers:
            handler()
        for handler in core.NewWindowRequested.handlers:
            requests.append(_NewWindowRequest())
            handler(None, requests[-1])

    fake = types.SimpleNamespace(settings={}, renderer="edgechromium", create_window=lambda *a, **k: win,
                                 start=start)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "6.2.1")
    monkeypatch.setattr(module, "_show_error", lambda message: pytest.fail(message))
    diagnostics = {}
    assert module.run_window(url, origin, diagnostics=diagnostics) == 0
    assert diagnostics["stage"] == "navigation-guard-installed" and "failure" not in diagnostics
    assert len(requests) == 1 and requests[0].handled is True
    assert loads == [url]
    assert fake.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is False
    outside = types.SimpleNamespace(Uri="https://example.com/", Cancel=False)
    core.NavigationStarting.handlers[0](None, outside)
    assert outside.Cancel is True
