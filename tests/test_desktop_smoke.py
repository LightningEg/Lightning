"""Packaged window checks start after guarded startup and still fail closed at every phase."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from lightning.desktop import window as desktop


class Startup:
    def __init__(self, ready=True):
        self.ready = ready
        self.waited = False

    def wait(self, timeout):
        assert timeout == desktop._STARTUP_TIMEOUT
        self.waited = True
        return self.ready


class Window:
    def __init__(self, startup, rejected, closed, *, health="ok", blocks=True, close=False):
        self.startup, self.rejected, self.closed = startup, rejected, closed
        self.health, self.blocks, self.close = health, blocks, close
        self.scripts = []

    def evaluate_js(self, script):
        assert self.startup.waited, "Do not evaluate scripts while WebView2 is still initializing"
        self.scripts.append(script)
        return True if script.startswith("Boolean(") else self.health

    def run_js(self, script):
        self.scripts.append(script)
        if script.startswith("location.href="):
            if self.blocks:
                self.rejected.set()
            if self.close:
                self.closed.set()


def run(*, ready=True, profile=True, health="ok", blocks=True, close=False, stale_rejection=False):
    startup, rejected, closed = Startup(ready), threading.Event(), threading.Event()
    if stale_rejection:
        rejected.set()
    window = Window(startup, rejected, closed, health=health, blocks=blocks, close=close)
    diagnostics = {}
    passed = desktop._check_smoke(window, profile_mode=profile, app_ready=startup, rejected=rejected,
                                  window_closed=closed, diagnostics=diagnostics)
    return passed, diagnostics, window


@pytest.mark.parametrize("profile, selector, path", [
    (True, "#profile-ready", "/profiles/health"),
    (False, "#probe-ready", "/api/check"),
])
def test_wait_for_guarded_startup_before_checking_page_health_and_navigation(profile, selector, path):
    passed, diagnostics, window = run(profile=profile)
    assert passed and diagnostics == {"smoke_stage": "passed"}
    assert any(selector in script for script in window.scripts)
    script = next(script for script in window.scripts if "fetch(" in script)
    assert path in script
    assert "r.ok&&new URL(r.url).origin===location.origin&&j.ok===true" in script
    assert "location.href='https://example.com/'" in window.scripts


def test_startup_timeout_fails_without_running_page_scripts():
    passed, diagnostics, window = run(ready=False)
    assert not passed and diagnostics == {"smoke_stage": "waiting-for-local-page"}
    assert not window.scripts


def test_cold_startup_does_not_consume_the_smoke_assertion_budget(monkeypatch):
    elapsed = [0]
    original_wait = Startup.wait

    def cold_wait(self, timeout):
        ready = original_wait(self, timeout)
        elapsed[0] += 25  # slower than the old 20-second smoke timer, within normal startup's 30
        return ready

    monkeypatch.setattr(Startup, "wait", cold_wait)
    monkeypatch.setattr(desktop, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))
    passed, diagnostics, _window = run()
    assert elapsed[0] == 25 and passed
    assert diagnostics == {"smoke_stage": "passed"}


def test_missing_marker_fails_before_the_health_request(monkeypatch):
    monkeypatch.setattr(desktop, "_SMOKE_TIMEOUT", 0)
    passed, diagnostics, window = run()
    assert not passed and diagnostics == {"smoke_stage": "waiting-for-page-marker"}
    assert not window.scripts


def test_bad_local_health_fails_without_attempting_external_navigation():
    passed, diagnostics, window = run(health="fail")
    assert not passed and diagnostics == {"smoke_stage": "checking-local-health"}
    assert not any(script.startswith("location.href=") for script in window.scripts)


def test_external_navigation_must_be_rejected_during_this_check():
    passed, diagnostics, _window = run(blocks=False, stale_rejection=True)
    assert not passed and diagnostics == {"smoke_stage": "checking-navigation-rejection"}


def test_closing_the_window_during_the_guard_check_is_not_a_pass():
    passed, diagnostics, _window = run(close=True)
    assert not passed and diagnostics == {"smoke_stage": "checking-navigation-rejection"}
