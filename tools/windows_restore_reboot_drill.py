"""Dummy-data restore drill across an ordinary Windows reboot.

Run ``prepare`` before reboot and ``verify`` after reboot. This is an operator
drill, not a power-cut simulation or a test against a real profile. Each phase
has its own encrypted dummy profile below the explicitly chosen drill folder.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# Keep the drill runnable as a script from any working directory, including
# the child processes used to stop at each phase.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lightning.database.promotion import PromotionPhase, SqlitePromotionJournalStore
from lightning.runtime.restore import RestoreManifest
from lightning.runtime.session import ProfileError, ProfileSession


PHASES = ("P0", "P1", "P2", "P3", "P4", "P5")
PASSWORD = "dummy-only restore reboot drill password"
QUESTION = "Dummy drill question?"
ANSWER = "dummy drill answer"
EXIT_AT_BOUNDARY = 73


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def boot_epoch() -> float:
    tick_count = ctypes.windll.kernel32.GetTickCount64
    tick_count.restype = ctypes.c_ulonglong
    return time.time() - tick_count() / 1000


def filesystem(path: Path) -> str:
    name = ctypes.create_unicode_buffer(256)
    get_volume = ctypes.windll.kernel32.GetVolumeInformationW
    get_volume.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
                           ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_wchar_p, ctypes.c_uint]
    get_volume.restype = ctypes.c_int
    result = get_volume(
        str(path.anchor), None, 0, None, None, None, name, len(name)
    )
    return name.value if result else "unknown"


def write_json(path: Path, record: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def crash_at(phase: str) -> None:
    """Patch one instance's durable boundary; process exit models interruption."""
    if phase == "P0":
        from lightning.runtime.restore import EncryptedBackupRestorer

        original = EncryptedBackupRestorer._write_restore_manifest

        def publish_then_exit(path, manifest, *, replace_existing=False):
            original(path, manifest, replace_existing=replace_existing)
            if manifest.state == "PENDING":
                os._exit(EXIT_AT_BOUNDARY)

        EncryptedBackupRestorer._write_restore_manifest = staticmethod(publish_then_exit)
    elif phase in ("P1", "P2", "P3"):
        expected = PromotionPhase(int(phase[1]))
        method = "prepare" if phase == "P1" else "advance"
        original = getattr(SqlitePromotionJournalStore, method)

        def persist_then_exit(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            journal = args[-1]
            if journal.phase is expected:
                os._exit(EXIT_AT_BOUNDARY)
            return result

        setattr(SqlitePromotionJournalStore, method, persist_then_exit)
    else:
        method = "commit_authority" if phase == "P4" else "mark_activated"
        original = getattr(SqlitePromotionJournalStore, method)

        def persist_then_exit(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            os._exit(EXIT_AT_BOUNDARY)

        setattr(SqlitePromotionJournalStore, method, persist_then_exit)


def prepare_one(folder: Path, phase: str) -> None:
    session = ProfileSession(folder / "profiles")
    session.prepare("Dummy", PASSWORD, PASSWORD, QUESTION, ANSWER)
    session.confirm(session.pending.recovery)
    live = session.paths.db_path
    session.container.settings.set("restore_drill", "saved backup")
    source = Path(session.container.backup_now())
    session.container.settings.set("restore_drill", "current live")
    session.close()
    write_json(folder / "input.json", {
        "phase": phase, "live": str(live), "source": str(source),
        "source_sha256": digest(source), "old_sha256": digest(live),
    })
    crash_at(phase)
    session.restore_backup(str(live), str(source), PASSWORD)
    raise RuntimeError(f"Restore reached completion without stopping at {phase}")


def prepare(folder: Path) -> None:
    if folder.exists():
        raise ValueError("Choose a new, empty drill folder so no earlier evidence is overwritten")
    folder.mkdir(parents=True)
    record = {
        "host": platform.node(), "system": platform.platform(),
        "filesystem": filesystem(folder), "boot_epoch": boot_epoch(),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "interruption": "os._exit(73) after each durable phase, then normal Windows Restart",
        "phases": {},
    }
    write_json(folder / "drill.json", record)
    for phase in PHASES:
        child = folder / phase
        child.mkdir()
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                 "_prepare_one", str(child), phase], check=False)
        if result.returncode != EXIT_AT_BOUNDARY:
            raise RuntimeError(f"{phase} setup exited {result.returncode}; keep {folder} for inspection")
        record["phases"][phase] = "interrupted"
        write_json(folder / "drill.json", record)
        print(f"{phase}: interrupted at durable boundary", flush=True)
    print(f"Reboot Windows normally, then run verify with this folder: {folder}", flush=True)


def verify_one(folder: Path, phase: str) -> dict:
    input_record = json.loads((folder / "input.json").read_text(encoding="utf-8"))
    live, source = Path(input_record["live"]), Path(input_record["source"])
    session = ProfileSession(folder / "profiles")
    paths = session._select(str(live))
    markers = list(paths.data_dir.glob(".lightning-restore-*.state"))
    if len(markers) != 1:
        raise AssertionError(f"{phase}: expected one durable restore manifest")
    manifest = RestoreManifest.from_bytes(markers[0].read_bytes())
    if manifest.state != "PENDING" or manifest.old_sha256 != input_record["old_sha256"]:
        raise AssertionError(f"{phase}: pending manifest or original checkpoint differs")
    journal_path = paths.data_dir / f".lightning-restore-{manifest.operation_id}.sqlite"
    if phase == "P0":
        if journal_path.exists():
            raise AssertionError("P0: journal exists before P1")
    else:
        state = SqlitePromotionJournalStore(journal_path).read_state()
        if state.journal is None or state.journal.phase != PromotionPhase(int(phase[1])):
            raise AssertionError(f"{phase}: journal did not survive reboot at its phase")
    if digest(source) != input_record["source_sha256"]:
        raise AssertionError(f"{phase}: selected dummy backup changed")
    try:
        session.unlock(str(live), PASSWORD)
    except ProfileError:
        pass
    else:
        session.close()
        raise AssertionError(f"{phase}: interrupted profile opened for writing before repair")
    if session.container is not None:
        raise AssertionError(f"{phase}: interrupted profile has a writable container")
    session.retry_at = 0.0
    session.resume_interrupted_restore(str(live), PASSWORD)
    if session.container is not None:
        raise AssertionError(f"{phase}: repair opened a writable container")
    completed = RestoreManifest.from_bytes(markers[0].read_bytes())
    expected_state = "ABANDONED" if phase == "P0" else "COMPLETE"
    if completed.state != expected_state:
        raise AssertionError(f"{phase}: expected {expected_state}, found {completed.state}")
    if digest(live) != (manifest.old_sha256 if phase == "P0" else manifest.candidate_sha256):
        raise AssertionError(f"{phase}: live ciphertext differs from accepted checkpoint")
    for name, expected in ((manifest.source_copy_name, manifest.source_copy_sha256),
                           (manifest.pre_restore_name, manifest.pre_restore_sha256)):
        evidence = paths.backups_dir / name
        if digest(evidence) != expected:
            raise AssertionError(f"{phase}: retained recovery evidence changed")
    session.unlock(str(live), PASSWORD)
    expected_value = "current live" if phase == "P0" else "saved backup"
    actual_value = session.container.settings.get("restore_drill")
    session.close()
    if actual_value != expected_value:
        raise AssertionError(f"{phase}: recovered profile contains {actual_value!r}")
    return {"result": "accepted checkpoint verified", "manifest": completed.state,
            "live_sha256": digest(live), "evidence": "retained and hash verified"}


def verify(folder: Path) -> None:
    record = json.loads((folder / "drill.json").read_text(encoding="utf-8"))
    if record["host"] != platform.node():
        raise RuntimeError("Verify on the same Windows PC as prepare")
    if abs(boot_epoch() - record["boot_epoch"]) < 10:
        raise RuntimeError("A Windows reboot has not been detected; reboot before verify")
    record["verified_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record["verified_boot_epoch"] = boot_epoch()
    for phase in PHASES:
        if record["phases"].get(phase) != "interrupted":
            raise RuntimeError(f"{phase} was not prepared")
        try:
            record["phases"][phase] = verify_one(folder / phase, phase)
            print(f"{phase}: recovered and verified", flush=True)
        except Exception as exc:
            record["phases"][phase] = {"result": "FAILED", "error": repr(exc)}
            write_json(folder / "drill.json", record)
            raise
        write_json(folder / "drill.json", record)
    print(f"All phases passed. Keep the evidence and share: {folder / 'drill.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify", "_prepare_one"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("phase", nargs="?", choices=PHASES)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This drill requires an ordinary Windows PC")
    folder = args.folder.resolve()
    if args.action == "prepare":
        prepare(folder)
    elif args.action == "verify":
        verify(folder)
    elif args.phase:
        prepare_one(folder, args.phase)
    else:
        parser.error("_prepare_one requires a phase")


if __name__ == "__main__":
    main()
