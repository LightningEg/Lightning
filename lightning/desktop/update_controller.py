"""What the Settings "Lightning version" block shows and does (NF-9B4): one small state machine over update.py,
update_guard.py and update_helper.py. Nothing runs until the person presses a button; the work happens on a worker
thread; the page polls `status()`. No figure here is money.

States: idle, checking, up_to_date, available, working, ready, refused_lend, refused_move, refused_folder, failed.
Every outside effect (network, disk, locking the profile, starting the helper, quitting) is injected, so the whole
flow runs on Linux in tests.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from lightning import DISPLAY_VERSION
from lightning.desktop import update as up
from lightning.desktop.update_guard import refusals
from lightning.desktop.update_helper import RealHost, Paths, mark_ok, repair


def available_here() -> bool:
    """Only the frozen Windows app updates itself; every other surface shows the version and the download page."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def folder_writable(install: Path) -> bool:
    """The swap renames the install folder inside its parent, so the parent must be writable (no admin rights asked)."""
    try:
        with tempfile.NamedTemporaryFile(dir=install.parent, prefix=".lightning-write-test-"):
            pass
        return os.access(install, os.W_OK)
    except OSError:
        return False


@dataclass
class UpdateController:
    install: Path
    updates: Path
    devices: object = None                       # lightning.runtime.devices.Devices (borrowed())
    profiles_root: Path | None = None
    borrowed_root: Path | None = None
    current: str = DISPLAY_VERSION
    after_update: str = ""                       # --after-update <old version>
    update_failed: str = ""                      # --update-failed <new version>
    check: Callable = up.check
    download: Callable = up.download
    stage: Callable = up.stage
    writable: Callable[[Path], bool] = folder_writable
    lock_profile: Callable[[], None] = lambda: None
    spawn: Callable[[list[str]], None] = lambda command: None
    quit: Callable[[], None] = lambda: None
    run_async: Callable[[Callable[[], None]], None] = lambda work: threading.Thread(target=work, daemon=True).start()
    _state: dict = field(default_factory=lambda: {"state": "idle"})
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _found: object = None
    _staged: Path | None = None
    _noticed: bool = False

    # --------------------------------------------------------------- what the page reads
    def status(self) -> dict:
        with self._lock:
            data = dict(self._state)
        data["current"] = self.current
        return data

    def take_notice(self) -> dict | None:
        """The one-time line after an update or a failed one; shown once."""
        if self._noticed:
            return None
        self._noticed = True
        if self.after_update:
            return {"kind": "updated", "version": self.current}
        if self.update_failed:
            return {"kind": "failed", "version": self.update_failed, "current": self.current}
        return None

    def _set(self, **data) -> None:
        with self._lock:
            self._state = data

    # --------------------------------------------------------------- the buttons
    def start_check(self) -> None:
        if self.status()["state"] in ("checking", "working"):
            return
        self._set(state="checking")
        self.run_async(self._check)

    def _check(self) -> None:
        result = self.check(current=self.current)
        if isinstance(result, up.UpToDate):
            self._set(state="up_to_date")
        elif isinstance(result, up.Available):
            self._found = result
            self._set(state="available", version=result.version, size_mb=max(1, round(result.size / 1_000_000)))
        else:
            self._set(state="failed", reason=result.reason)

    def start_download(self) -> None:
        found = self._found
        if self.status()["state"] != "available" or found is None:
            return
        self._set(state="working", phase="downloading", percent=0, version=found.version)
        self.run_async(lambda: self._download(found))

    def _download(self, found) -> None:
        try:
            def progress(done, total):
                self._set(state="working", phase="downloading", percent=int(100 * done / total), version=found.version)
            zip_path = self.download(found, self.updates, progress=progress)
            self._set(state="working", phase="verifying", percent=100, version=found.version)
            self._staged = self.stage(zip_path, found.version)
            self._set(state="ready", version=found.version)
        except up.UpdateError as error:
            self._set(state="failed", reason=str(error))
        except OSError:
            self._set(state="failed", reason="Lightning could not save the update on this PC.")

    def restart(self) -> None:
        """Refuse for a reason the person can act on, else lock the profile, start the staged helper and quit."""
        if self.status()["state"] not in ("ready", "refused_lend", "refused_move", "refused_folder") or self._staged is None:
            return
        version = self._found.version
        for refusal in refusals(self.devices, self.profiles_root, self.borrowed_root) if self.devices is not None else []:
            if refusal.kind == "lend":
                return self._set(state="refused_lend", names=list(refusal.names), version=version)
            return self._set(state="refused_move", names=list(refusal.names), version=version)
        if not self.writable(self.install):
            return self._set(state="refused_folder", version=version)
        try:
            self.lock_profile()
            self.spawn([str(self._staged / "Lightning.exe"), "--finish-update", "--install", str(self.install),
                        "--old-pid", str(os.getpid()), "--from", self.current])
        except Exception:  # noqa: BLE001 - never leave the person locked out with no word
            return self._set(state="failed", reason="Lightning could not start the update.")
        self.quit()

    # --------------------------------------------------------------- the app's own start
    def startup(self) -> None:
        """Called once when the app starts: leave one working folder after a crash, tidy a finished update."""
        paths = Paths(self.install, self.updates / "none", self.updates)
        repair(RealHost(), paths)
        if self.after_update:
            for child in self.updates.glob("*"):
                if child.is_dir() and child.name != "ok":
                    shutil.rmtree(child, ignore_errors=True)

    def chooser_loaded(self) -> None:
        """The profile chooser answered: tell the helper the new version started (before any unlock or migration)."""
        if self.after_update:
            mark_ok(self.updates, self.current)


def for_this_app(after_update: str = "", update_failed: str = "") -> UpdateController | None:
    """The controller of the frozen Windows app, or None everywhere else (the block then offers the download page)."""
    if not available_here():
        return None
    import subprocess
    from lightning.runtime.paths import app_data_root

    def spawn(command: list[str]) -> None:
        subprocess.Popen(command, cwd=Path(command[0]).parent, close_fds=True,
                         creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    return UpdateController(Path(sys.executable).resolve().parent, app_data_root() / "updates",
                            after_update=after_update, update_failed=update_failed, spawn=spawn,
                            quit=lambda: threading.Timer(1.0, os._exit, [0]).start())  # after the page has been sent
