"""A copy outside the app (BT-2AI3): the phone keeps the newest profile files in a folder the person chose.

Android deletes an app's own storage when the app is removed, and a changed app identity leaves it behind. The
person picks a folder once (the system's folder picker, no storage permission); after that, once a day per
profile, Lightning writes a profile file (BT-2AI5) there and keeps the newest three it wrote. The folder survives
an uninstall; "Open a profile file" (BT-2AI2) brings the book back. Java only moves bytes: what to write, when,
and what to prune is decided here, so it is tested without a phone.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
from pathlib import Path
from typing import Protocol

LOG = logging.getLogger("lightning")
KEEP = 3
FOLDER_LOST = "The folder is gone, or Lightning may no longer use it. Choose it again."
WRITE_FAILED = "The copy could not be saved there. Check the folder and its free space."


class FolderBridge(Protocol):
    def state(self) -> tuple[str, str]: ...        # ("none" | "ok" | "lost", the folder's name)
    def choose(self) -> None: ...                  # show the system's folder picker
    def forget(self) -> None: ...                  # give the folder's permission back
    def write(self, path: str, name: str) -> str: ...  # the name the file got in the folder, or "" when it failed
    def names(self) -> list[str]: ...              # the files in the folder
    def delete(self, name: str) -> bool: ...


def _today() -> str:
    from lightning.core.dates import fmt_date, today
    return fmt_date(today())  # the app's own day, so Settings can say "Today"


class OutsideCopy:
    def __init__(self, bridge: FolderBridge, staging: str | Path, state_path: str | Path):
        self.bridge, self.staging, self.state_path = bridge, Path(staging), Path(state_path)
        shutil.rmtree(self.staging, ignore_errors=True)  # nothing left by a closed app is ever written out

    # -- what the phone remembers: per profile, the day and folder of its last copy and the names it wrote ------
    def _read(self) -> dict:
        try:
            document = json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {"profiles": {}, "problem": ""}
        if not isinstance(document, dict) or not isinstance(document.get("profiles"), dict):
            return {"profiles": {}, "problem": ""}
        document.setdefault("problem", "")
        return document

    def _save(self, document: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(f".{self.state_path.name}.{secrets.token_hex(8)}")
        temporary.write_text(json.dumps(document, sort_keys=True), "utf-8")
        os.replace(temporary, self.state_path)

    # -- Settings ------------------------------------------------------------------------------------------
    def status(self, profile_id: str = "") -> dict:
        """For Settings › Backup: whether a folder is chosen, its name, the open profile's last copy, a problem."""
        state, name = self.bridge.state()
        document = self._read()
        entry = document["profiles"].get(profile_id, {})
        last = entry.get("date", "") if state == "ok" and entry.get("folder") == name else ""
        problem = FOLDER_LOST if state == "lost" else (document["problem"] if state == "ok" else "")
        return {"chosen": state != "none", "folder": name, "last": last, "problem": problem}

    def choose(self) -> None:
        document = self._read()
        document["problem"] = ""
        document.pop("tried", None)  # a folder chosen again is tried again at once
        self._save(document)
        self.bridge.choose()

    def stop(self) -> None:
        """Stop keeping copies. The files already in the folder stay: they are the person's."""
        self.bridge.forget()
        self._save({"profiles": {}, "problem": ""})

    # -- the copy itself -----------------------------------------------------------------------------------
    def keep(self, session) -> bool:
        """Write today's copy of the open profile if it is due; True when one was written. Never raises: a
        failed copy is a line in Settings, never a broken page."""
        try:
            return self._keep(session)
        except Exception as exc:  # noqa: BLE001 - the page that triggered this must still open
            LOG.warning("outside copy failed: %s", type(exc).__name__)
            try:
                document = self._read()
                document["problem"] = WRITE_FAILED
                self._save(document)
            except OSError:
                pass
            return False

    def _keep(self, session) -> bool:
        paths = getattr(session, "paths", None)
        profile = getattr(paths, "profile", None)
        if session.container is None or profile is None or session.borrowed is not None \
                or not session.container.db.encrypted:
            return False
        state, folder = self.bridge.state()
        if state != "ok":
            return False
        document = self._read()
        entry = document["profiles"].get(profile.profile_id, {})
        same_folder = entry.get("folder") == folder
        if same_folder and entry.get("date") == _today():
            return False
        if document.get("tried") == [profile.profile_id, folder, _today()]:
            return False  # it failed today already: try again tomorrow, or when the folder is chosen again
        document["tried"] = [profile.profile_id, folder, _today()]
        self._save(document)
        self.staging.mkdir(parents=True, exist_ok=True)
        saved = session.write_profile_file(self.staging)
        try:
            written = self.bridge.write(str(saved), saved.name)
        finally:
            saved.unlink(missing_ok=True)
        if not written:
            document["problem"] = WRITE_FAILED
            self._save(document)
            return False
        # Names from another folder are not ours to prune here: a new folder starts its own list.
        names = [name for name in entry.get("written", []) if isinstance(name, str)] if same_folder else []
        names = [name for name in names if name != written] + [written]
        present = set(self.bridge.names())
        kept = []
        for index, name in enumerate(names):
            old = index < len(names) - KEEP
            if old and name.endswith(".lightning") and name in present and not self.bridge.delete(name):
                kept.append(name)  # could not delete it now: try again with the next copy
            elif not old:
                kept.append(name)
        document["profiles"][profile.profile_id] = {"date": _today(), "folder": folder, "written": kept}
        document["problem"] = ""
        document.pop("tried", None)
        self._save(document)
        return True
