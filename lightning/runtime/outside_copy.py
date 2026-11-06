"""BT-2AI3: a copy of the profile outside the app, so an uninstall never takes the only copy with it.

Once, the person chooses a folder (Android's own folder screen, which the app may keep using). After each day's
first change a `.lightning` file (see `profile_file`) is written there and the newest three are kept. Opening a
profile file (2AI2) turns that copy back into the book. On a PC nothing here runs: its profile folder is already
in Documents, outside the app.
"""
from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from lightning.runtime.profile_file import SUFFIX, export_profile_file

LOG = logging.getLogger("lightning")
KEEP = 3


class OutsideFolder(Protocol):
    def chosen(self) -> bool: ...   # a folder is chosen and still allowed
    def choose(self) -> bool: ...   # show the folder screen; True when it is shown
    def write(self, prefix: str, name: str, path: str) -> bool: ...  # copy the file in; keep the newest KEEP


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class OutsideCopy:
    def __init__(self, state_path: Path, folder: OutsideFolder, scratch: Path):
        self.state_path, self.folder, self.scratch = Path(state_path), folder, Path(scratch)

    def _state(self) -> dict:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def last(self, profile_id: str) -> str:
        """The day (yyyy-mm-dd) of this profile's last copy, or ''."""
        found = self._state().get(profile_id, "")
        return found if isinstance(found, str) else ""

    def row(self, profile_id: str) -> str:
        """For Settings › This phone: 'on' (a folder is chosen) or 'off'."""
        try:
            return "on" if self.folder.chosen() else "off"
        except Exception:
            return "off"

    def due(self, profile_id: str) -> bool:
        try:
            return self.folder.chosen() and self.last(profile_id) != _today()
        except Exception:
            return False

    def write(self, paths, db) -> bool:
        """Write today's copy. Never raises: a copy that fails is tried again on the next change."""
        info = paths.profile
        if info is None:
            return False
        day = _today()
        try:
            self.scratch.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.scratch) as work:
                made = export_profile_file(paths, db, Path(work) / f"{info.name}_{day}{SUFFIX}")
                if not self.folder.write(info.name + "_", made.name, str(made)):
                    return False
        except Exception:
            LOG.exception("The copy outside the app could not be written")
            return False
        state = self._state()
        state[info.profile_id] = day
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(state), encoding="utf-8")
        except OSError:
            pass
        return True
