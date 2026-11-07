"""The update helper: swap the install folder for the staged one, and put the old one back if the new one fails (NF-9B3).

Runs from the staged folder (`staged\\Lightning.exe --finish-update --install <folder> --old-pid <pid> --from <version>`),
so the install folder is free to rename. All the logic is platform-neutral; every operating-system call goes through the
`Host` object, so tests drive it with a fake disk and fake processes, including a power cut between any two steps.

Folders beside the install folder `<install>`: `.previous` (the old version, kept until the next update), `.incoming`
(the copy being checked), `.failed` (a new version that did not start). `update.json` in the updates folder says how far
the swap got, so `repair()` leaves exactly one working folder after a crash. Nothing here touches profiles or borrowed
copies, and nothing personal is logged.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

WAIT_OLD_EXIT, RENAME_TRIES, RENAME_PAUSE, WAIT_NEW_START = 60.0, 10, 1.0, 90.0


class Host(Protocol):
    def exists(self, path: Path) -> bool: ...
    def rename(self, source: Path, target: Path) -> None: ...
    def rmtree(self, path: Path) -> None: ...
    def copytree(self, source: Path, target: Path) -> None: ...
    def read_text(self, path: Path) -> str: ...
    def write_text(self, path: Path, text: str) -> None: ...
    def append_log(self, path: Path, line: str) -> None: ...
    def file_hashes(self, folder: Path) -> dict[str, str]: ...
    def pid_alive(self, pid: int) -> bool: ...
    def launch(self, exe: Path, args: list[str]) -> object: ...
    def exited(self, process: object) -> bool: ...
    def terminate(self, process: object) -> None: ...
    def sleep(self, seconds: float) -> None: ...
    def now(self) -> float: ...


@dataclass(frozen=True)
class Paths:
    install: Path
    staged: Path
    updates: Path

    @property
    def previous(self) -> Path: return self.install.with_name(self.install.name + ".previous")
    @property
    def incoming(self) -> Path: return self.install.with_name(self.install.name + ".incoming")
    @property
    def failed(self) -> Path: return self.install.with_name(self.install.name + ".failed")
    @property
    def state(self) -> Path: return self.updates / "update.json"
    @property
    def log(self) -> Path: return self.updates / "update.log"

    def ok_marker(self, version: str) -> Path: return self.updates / f"ok-{version}"
    @property
    def exe(self) -> Path: return self.install / "Lightning.exe"


def _log(host: Host, paths: Paths, line: str) -> None:
    host.append_log(paths.log, f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(host.now()))} {line}")


def _set_step(host: Host, paths: Paths, step: str, old: str, new: str) -> None:
    host.write_text(paths.state, json.dumps({"step": step, "from": old, "to": new}))


def _read_step(host: Host, paths: Paths) -> dict:
    try:
        data = json.loads(host.read_text(paths.state))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _rename_retrying(host: Host, source: Path, target: Path) -> bool:
    """Antivirus or Explorer may hold files for a moment: ten tries over ten seconds."""
    for attempt in range(RENAME_TRIES):
        try:
            host.rename(source, target)
            return True
        except OSError:
            if attempt + 1 < RENAME_TRIES:
                host.sleep(RENAME_PAUSE)
    return False


def _rollback(host: Host, paths: Paths) -> None:
    """The new folder (if any) becomes `.failed`; `.previous` becomes the install folder again."""
    if host.exists(paths.install):
        if host.exists(paths.failed):
            host.rmtree(paths.failed)
        host.rename(paths.install, paths.failed)
    host.rename(paths.previous, paths.install)


def repair(host: Host, paths: Paths) -> str:
    """After a crash or power cut: leave one working folder. Returns what it did ("nothing", "restored", "cleaned",
    "rolled back" or "accepted")."""
    did = "nothing"
    if not host.exists(paths.install) and host.exists(paths.previous):
        host.rename(paths.previous, paths.install)
        did = "restored"
    if host.exists(paths.incoming):
        host.rmtree(paths.incoming)
        did = "cleaned" if did == "nothing" else did
    state = _read_step(host, paths)
    if state.get("step") in ("swapped", "launched") and host.exists(paths.previous) and host.exists(paths.install):
        if host.exists(paths.ok_marker(str(state.get("to")))):
            _set_step(host, paths, "ok", str(state.get("from")), str(state.get("to")))
            did = "accepted"
        else:
            _rollback(host, paths)
            _set_step(host, paths, "failed", str(state.get("from")), str(state.get("to")))
            did = "rolled back"
    return did


def verify_copy(host: Host, folder: Path) -> bool:
    """Every file `FILES.sha256` lists is present and identical, and nothing else is there."""
    try:
        listed = {}
        for line in host.read_text(folder / "FILES.sha256").splitlines():
            digest, _, name = line.partition("  ")
            listed[name] = digest
    except OSError:
        return False
    actual = host.file_hashes(folder)
    actual.pop("FILES.sha256", None)
    return bool(listed) and listed == actual


def run(host: Host, paths: Paths, *, old_pid: int, old_version: str, new_version: str) -> str:
    """The whole swap. Returns "updated", "old app still open", "rename blocked", "copy corrupt" or "new app failed";
    in every case but the first the old version is what is left in the install folder."""
    log = lambda line: _log(host, paths, line)  # noqa: E731
    log(f"update {old_version} to {new_version} begins")
    deadline = host.now() + WAIT_OLD_EXIT
    while host.pid_alive(old_pid):
        if host.now() >= deadline:
            log("the old app did not close; nothing was changed")
            return "old app still open"
        host.sleep(0.5)
    repair(host, paths)
    _set_step(host, paths, "renaming", old_version, new_version)
    if host.exists(paths.previous):
        host.rmtree(paths.previous)
    if not _rename_retrying(host, paths.install, paths.previous):
        log("the install folder could not be renamed; the old app is relaunched")
        host.launch(paths.exe, ["--update-failed", new_version])
        return "rename blocked"
    log("old version kept as .previous")
    try:
        if host.exists(paths.incoming):
            host.rmtree(paths.incoming)
        host.copytree(paths.staged, paths.incoming)
        if not verify_copy(host, paths.incoming):
            raise OSError("the copy differs from FILES.sha256")
        _set_step(host, paths, "swapped", old_version, new_version)
        host.rename(paths.incoming, paths.install)
    except OSError as error:
        log(f"the copy failed ({type(error).__name__}); going back")
        if host.exists(paths.incoming):
            host.rmtree(paths.incoming)
        _set_step(host, paths, "failed", old_version, new_version)
        host.rename(paths.previous, paths.install)
        host.launch(paths.exe, ["--update-failed", new_version])
        return "copy corrupt"
    log("new version in place; starting it")
    _set_step(host, paths, "launched", old_version, new_version)
    process = host.launch(paths.exe, ["--after-update", old_version])
    deadline = host.now() + WAIT_NEW_START
    while not host.exists(paths.ok_marker(new_version)):
        if host.exited(process) or host.now() >= deadline:
            log("the new version did not reach its profile chooser; going back")
            if not host.exited(process):
                host.terminate(process)
            _rollback(host, paths)
            _set_step(host, paths, "failed", old_version, new_version)
            host.launch(paths.exe, ["--update-failed", new_version])
            return "new app failed"
        host.sleep(0.5)
    _set_step(host, paths, "ok", old_version, new_version)
    log("the new version started; .previous is kept until the next update")
    return "updated"


def mark_ok(updates: Path, version: str) -> None:
    """The new app calls this once its profile chooser has loaded (before any unlock or migration)."""
    updates.mkdir(parents=True, exist_ok=True)
    (updates / f"ok-{version}").write_text("ok\n", encoding="utf-8")


class RealHost:
    """The operating system, for the frozen Windows app."""

    def exists(self, path): return path.exists()
    def rename(self, source, target): os.rename(source, target)
    def rmtree(self, path): shutil.rmtree(path)
    def copytree(self, source, target): shutil.copytree(source, target)
    def read_text(self, path): return path.read_text(encoding="utf-8")

    def write_text(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)

    def append_log(self, path, line):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    def file_hashes(self, folder):
        return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def pid_alive(self, pid):
        if sys.platform == "win32":
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if not handle:
                return False
            try:
                return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def launch(self, exe, args): return subprocess.Popen([str(exe), *args], cwd=exe.parent)
    def exited(self, process): return process.poll() is not None
    def terminate(self, process): process.terminate()
    def sleep(self, seconds): time.sleep(seconds)
    def now(self): return time.time()


def main(install: Path, old_pid: int, old_version: str, *, staged: Path | None = None, updates: Path | None = None,
         host: Host | None = None) -> int:
    """Entry for `--finish-update`: the staged folder is where this program runs from."""
    staged = staged or Path(sys.executable).resolve().parent
    updates = updates or staged.parent
    new_version = staged.parent.name  # updates\<version>\staged
    result = run(host or RealHost(), Paths(install, staged, updates), old_pid=old_pid, old_version=old_version,
                 new_version=new_version)
    return 0 if result == "updated" else 1
