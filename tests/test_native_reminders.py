"""IT-2C5: the Windows reminder balloons that run while the app is open, tested with fakes on any OS."""

from __future__ import annotations

import json
import sys
import threading
import types
from datetime import date

import pytest

from lightning.desktop import window as desktop_window

ORIGIN = "http://127.0.0.1:8765"
ALLOWED = ("http", "127.0.0.1", 8765)


def test_prefs_missing_corrupt_or_wrong_shape_read_as_empty(tmp_path):
    path = tmp_path / "native-reminders.json"
    assert desktop_window._read_reminder_prefs(path) == {}
    path.write_text("{not json", encoding="utf-8")
    assert desktop_window._read_reminder_prefs(path) == {}
    path.write_text("[1, 2]", encoding="utf-8")
    assert desktop_window._read_reminder_prefs(path) == {}
    path.write_text(json.dumps({"seen": ["a"]}), encoding="utf-8")
    assert desktop_window._read_reminder_prefs(path) == {}


def test_prefs_round_trip(tmp_path):
    path = tmp_path / "nested" / "native-reminders.json"
    desktop_window._write_reminder_prefs(path, {"bill:1": "2026-11-10"})
    assert desktop_window._read_reminder_prefs(path) == {"bill:1": "2026-11-10"}


class _Native:
    def __init__(self):
        self.calls = []

    def BeginInvoke(self, action):  # noqa: N802 - the .NET name
        self.calls.append(action)


class _Window:
    def __init__(self, payload, closed):
        self.payload, self.closed, self.native = payload, closed, _Native()

    def run_js(self, _script):
        return None

    def evaluate_js(self, _script):
        self.closed.set()  # one poll, then the loop ends
        return json.dumps(self.payload)


def _run(payload, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "System", types.SimpleNamespace(Action=lambda f: f))
    monkeypatch.setattr(desktop_window, "_reminder_prefs_path", lambda: tmp_path / "prefs.json")
    ready, closed = threading.Event(), threading.Event()
    ready.set()
    window = _Window(payload, closed)
    desktop_window._native_reminder_loop(window, ORIGIN, ALLOWED, ready, closed, {"icon": object(), "href": None})
    return window.native.calls, desktop_window._read_reminder_prefs(tmp_path / "prefs.json")


GOOD = {"id": "bill:7", "href": "/bills", "label": "Rent is due", "detail": "Today"}


def test_one_balloon_for_the_first_valid_item(monkeypatch, tmp_path):
    second = dict(GOOD, id="bill:8")
    calls, seen = _run({"enabled": True, "items": [GOOD, second]}, monkeypatch, tmp_path)
    assert len(calls) == 1
    assert seen == {"bill:7": date.today().isoformat()}


def test_none_when_disabled(monkeypatch, tmp_path):
    calls, seen = _run({"enabled": False, "items": [GOOD]}, monkeypatch, tmp_path)
    assert calls == [] and seen == {}


@pytest.mark.parametrize("bad", [
    dict(GOOD, id="bad id!"),
    dict(GOOD, href="https://example.com/"),
    dict(GOOD, href="//example.com/x"),
    dict(GOOD, label="   "),
    "not an item",
])
def test_bad_items_are_skipped(bad, monkeypatch, tmp_path):
    calls, seen = _run({"enabled": True, "items": [bad]}, monkeypatch, tmp_path)
    assert calls == [] and seen == {}


def test_bad_item_does_not_hide_the_next_good_one(monkeypatch, tmp_path):
    calls, seen = _run({"enabled": True, "items": [dict(GOOD, id="x", href="https://example.com/"), GOOD]},
                       monkeypatch, tmp_path)
    assert len(calls) == 1 and list(seen) == ["bill:7"]


def test_an_item_seen_today_is_not_shown_again(monkeypatch, tmp_path):
    desktop_window._write_reminder_prefs(tmp_path / "prefs.json", {"bill:7": date.today().isoformat()})
    calls, _seen = _run({"enabled": True, "items": [GOOD]}, monkeypatch, tmp_path)
    assert calls == []


def test_an_item_seen_yesterday_is_shown(monkeypatch, tmp_path):
    desktop_window._write_reminder_prefs(tmp_path / "prefs.json", {"bill:7": "2000-01-01"})
    calls, seen = _run({"enabled": True, "items": [GOOD]}, monkeypatch, tmp_path)
    assert len(calls) == 1 and seen == {"bill:7": date.today().isoformat()}
