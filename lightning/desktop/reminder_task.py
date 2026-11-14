"""NF-3AU3: reminders with the app closed on Windows. A per-user scheduled task runs ``Lightning.exe --remind`` once a
day; that run reads the reminder schedule the open app wrote (``workflows/reminder_schedule.py``: days, kinds and opaque
ids only, never a figure or a name), shows one Windows notification for today's items, notes their ids in
``native-reminders.json`` so the open app does not repeat them, and exits without a window or a profile. A missing or
stale schedule shows nothing. No admin rights: ``schtasks`` creates the task for the signed-in user."""
from __future__ import annotations

import subprocess
from datetime import date, timedelta
from pathlib import Path

from lightning.core.dates import today

from lightning.workflows.reminder_schedule import KIND_TEXT, default_path, read

TASK = "Lightning reminders"
AT = "09:00"
STALE_DAYS = 14   # a schedule not rewritten for two weeks belongs to a profile no longer opened: say nothing


def register(exe: str, run=subprocess.run) -> bool:
    """Create (or replace) the daily task. Called when reminders are turned on in the Windows app."""
    command = ["schtasks", "/Create", "/SC", "DAILY", "/ST", AT, "/TN", TASK, "/TR", f'"{exe}" --remind', "/F"]
    return _quiet(run, command)


def unregister(run=subprocess.run) -> bool:
    """Delete the task. Called when reminders are turned off."""
    return _quiet(run, ["schtasks", "/Delete", "/TN", TASK, "/F"])


def switch(enabled: bool) -> None:
    """The Windows app's hook for ``reminder_schedule.switched``: the packaged exe runs ``--remind`` daily."""
    import sys
    if not getattr(sys, "frozen", False):   # a source run has no exe to schedule
        return
    register(sys.executable) if enabled else unregister()


def _quiet(run, command: list[str]) -> bool:
    try:
        return run(command, check=False, capture_output=True, timeout=30,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def message(kinds: list[str]) -> str:
    """One sentence for today's items: the kind's own sentence for one, a count for several. Never a name or figure."""
    if len(kinds) == 1:
        return KIND_TEXT[kinds[0]]
    return f"{len(kinds)} things are due tomorrow."


def remind(path: Path | None = None, prefs: Path | None = None, notify=None, day: date | None = None) -> int:
    """The ``--remind`` run: notify once for today's items not yet shown; returns how many items it announced."""
    from lightning.desktop.window import _read_reminder_prefs, _reminder_prefs_path, _write_reminder_prefs
    path, prefs, day = path or default_path(), prefs or _reminder_prefs_path(), day or today()
    data = read(path) if path else None
    if not data:
        return 0
    try:
        written = date.fromisoformat(str(data.get("written", "")))
    except ValueError:
        return 0
    if day - written > timedelta(days=STALE_DAYS):
        return 0
    seen = {key: value for key, value in _read_reminder_prefs(prefs).items() if value == day.isoformat()}
    due = [item for item in data.get("items", []) if isinstance(item, dict) and item.get("day") == day.isoformat()
           and item.get("kind") in KIND_TEXT and str(item.get("id", "")) not in seen]
    if not due:
        return 0
    (notify or _windows_notify)(message([item["kind"] for item in due]))
    seen.update({str(item["id"]): day.isoformat() for item in due})
    _write_reminder_prefs(prefs, seen)
    return len(due)


def _windows_notify(text: str) -> None:
    """A tray balloon from a short-lived process (the same Windows Forms notice the open app shows)."""
    try:
        import time

        import clr  # noqa: F401 - pythonnet, shipped with the Windows app
        from System.Drawing import SystemIcons
        from System.Windows.Forms import NotifyIcon, ToolTipIcon
        icon = NotifyIcon()
        icon.Icon = SystemIcons.Information
        icon.Visible = True
        icon.BalloonTipTitle = "Lightning"
        icon.BalloonTipText = text
        icon.BalloonTipIcon = ToolTipIcon.Info
        icon.ShowBalloonTip(8000)
        time.sleep(8)
        icon.Dispose()
    except Exception:  # noqa: BLE001 - a notice is a convenience; the task never fails loudly
        pass
