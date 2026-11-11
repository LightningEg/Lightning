"""NF-3AU3: the Windows daily task. Its schtasks lines (no admin rights), and the --remind run: one notice with no
figure for today's items, nothing for a missing or stale schedule, nothing twice."""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from lightning.desktop import reminder_task
from lightning.workflows import reminder_schedule


def test_register_and_unregister_run_the_per_user_schtasks_lines():
    calls = []
    run = lambda command, **kw: calls.append((command, kw)) or SimpleNamespace(returncode=0)  # noqa: E731
    assert reminder_task.register(r"C:\Program Files\Lightning\Lightning.exe", run=run)
    assert reminder_task.unregister(run=run)
    assert calls[0][0] == ["schtasks", "/Create", "/SC", "DAILY", "/ST", "09:00", "/TN", "Lightning reminders",
                           "/TR", '"C:\\Program Files\\Lightning\\Lightning.exe" --remind', "/F"]
    assert calls[1][0] == ["schtasks", "/Delete", "/TN", "Lightning reminders", "/F"]
    assert "/RL" not in calls[0][0] and all(kw["check"] is False for _, kw in calls)   # never elevated, never raises


def _schedule(tmp_path, written: str, items: list[dict]):
    path = tmp_path / "reminder-schedule.json"
    path.write_text(json.dumps({"version": reminder_schedule.VERSION, "profile": "p", "written": written,
                                "items": items}), encoding="utf-8")
    return path


def test_remind_notifies_once_for_today_with_no_figure_and_not_twice(tmp_path):
    path = _schedule(tmp_path, "2026-11-10", [{"day": "2026-11-11", "kind": "payment", "id": "a1"},
                                              {"day": "2026-11-11", "kind": "zakat", "id": "b2"},
                                              {"day": "2026-11-12", "kind": "payment", "id": "c3"}])
    prefs, shown = tmp_path / "native-reminders.json", []
    assert reminder_task.remind(path, prefs, shown.append, date(2026, 11, 11)) == 2
    assert shown == ["2 things are due tomorrow."] and not any(ch.isdigit() for ch in shown[0][1:])
    assert json.loads(prefs.read_text())["seen"] == {"a1": "2026-11-11", "b2": "2026-11-11"}  # the open app skips them
    assert reminder_task.remind(path, prefs, shown.append, date(2026, 11, 11)) == 0 and len(shown) == 1
    assert reminder_task.remind(path, prefs, shown.append, date(2026, 11, 12)) == 1
    assert shown[-1] == "A payment is due tomorrow."


def test_a_missing_or_stale_schedule_shows_nothing(tmp_path):
    shown = []
    assert reminder_task.remind(tmp_path / "none.json", tmp_path / "p.json", shown.append, date(2026, 11, 11)) == 0
    stale = _schedule(tmp_path, "2026-10-01", [{"day": "2026-11-11", "kind": "payment", "id": "a1"}])
    assert reminder_task.remind(stale, tmp_path / "p.json", shown.append, date(2026, 11, 11)) == 0
    assert shown == []


def test_turning_reminders_on_or_off_reaches_the_windows_hook(c):
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    heard = []
    reminder_schedule.ON_SWITCH.append(heard.append)
    try:
        client = TestClient(create_app(c))
        client.post("/reminders/settings", data={"enabled": "1"})
        client.post("/reminders/settings", data={"enabled": "0"})
    finally:
        reminder_schedule.ON_SWITCH.remove(heard.append)
    assert heard == [True, False]


def test_the_exe_s_remind_flag_exits_without_a_window(monkeypatch):
    from lightning.desktop import app
    ran = []
    monkeypatch.setattr(reminder_task, "remind", lambda *a, **k: ran.append(True) or 0)
    assert app.run(["--remind"]) == 0 and ran == [True]
