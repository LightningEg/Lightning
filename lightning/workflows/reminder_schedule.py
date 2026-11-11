"""NF-3AU2: the reminder schedule, written while a profile is open so Windows and Android can announce what is due with
the app closed (owner, 2026-11-08: days and kinds only). The file holds dates, kinds and opaque ids, never a figure, an
account, a payee or a category: the encrypted profile cannot be read with the app closed, and this file is not
encrypted. The kinds become the fixed sentences in ``KIND_TEXT``, translated when they are shown."""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from lightning.core.dates import today

VERSION = 1
FILE_NAME = "reminder-schedule.json"
ENV = "LIGHTNING_REMINDER_SCHEDULE"   # the Android shell sets it under the app's files dir (3AU4)

# What a closed-app notice says for each kind; one sentence each, never a name or a figure.
KIND_TEXT = {
    "payment": "A payment is due tomorrow.",
    "gameya": "A gam'eya instalment is due tomorrow.",
    "zakat": "Zakat day is tomorrow.",
}


def default_path() -> Path | None:
    """Where this device keeps the schedule: the path the shell names, else next to ``native-reminders.json`` on
    Windows (``%LOCALAPPDATA%/Lightning``). Elsewhere nothing announces reminders with the app closed: no file."""
    named = os.environ.get(ENV, "").strip()
    if named:
        return Path(named)
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return root / "Lightning" / FILE_NAME
    return None


def write(path: Path, items: list[dict], profile_id: str, day: date | None = None) -> None:
    """Write the schedule atomically (a temp file, then ``replace``). ``items`` are ``ReminderService.upcoming()``'s;
    only their day, kind and id are kept, so nothing else can slip in."""
    kept = [{"day": str(i["day"]), "kind": str(i["kind"]), "id": str(i["id"])} for i in items if i.get("kind") in KIND_TEXT]
    body = {"version": VERSION, "profile": profile_id, "written": (day or today()).isoformat(), "items": kept}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def clear(path: Path) -> None:
    path.unlink(missing_ok=True)


def read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("version") == VERSION else None


def refresh(c, path: Path | None = None, *, force: bool = False) -> bool:
    """Bring the schedule up to date for the open profile: written when reminders are on (at most once a day unless
    ``force``), removed when they are off. Returns whether the file was written. Never raises: a reminder file is a
    convenience and must not break the page or the lock that asked for it."""
    from lightning.workflows.reminders import ReminderService
    path = path or default_path()
    if path is None:
        return False
    try:
        service = ReminderService(c)
        if c.settings.get("reminders_enabled") != "1":
            clear(path)
            return False
        if not service.enabled:   # read-only or closing: leave what an earlier session wrote
            return False
        profile = service.profile_hash()
        current = read(path)
        if not force and current and current.get("written") == today().isoformat() and current.get("profile") == profile:
            return False
        write(path, service.upcoming(), profile)
        return True
    except Exception:  # noqa: BLE001 - see the docstring
        return False
