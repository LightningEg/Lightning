"""Ordinary Windows reboot drill for encrypted dummy promotion data.

Run `prepare --root <new-empty-local-folder> --phase P3`, reboot Windows, then
run `resume --root <same-folder>`. This exercises one real durable phase across
a normal OS restart; it is not a power-cut test. Never point it at user data.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path

# Direct execution sets sys.path to tools/, not the checkout root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from lightning.bootstrap import build
from lightning.database.connection import Database
from lightning.database.migrator import inspect_schema
from lightning.database.promotion import (
    CandidatePromotionService, PromotionPhase, SqlitePromotionJournalStore,
)
from lightning.database.promotion_windows import WindowsPromotionFileOps
from lightning.database.snapshot import verify_connection
from lightning.database.staging import stage_database

# Public, disposable drill key. It is never suitable for a real profile.
DUMMY_KEY = bytes.fromhex("5a" * 32)
LIVE = "dummy-profile.db"
CANDIDATE = "dummy-candidate.partial"
PREVIOUS = "dummy-previous.db"
CONTROL = "promotion-control.sqlite"
RECORD = "drill-evidence.json"


class Gate:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def boot_marker() -> int:
    """Approximate Windows boot epoch using the monotonic uptime counter."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetTickCount64.argtypes = ()
    kernel.GetTickCount64.restype = ctypes.c_ulonglong
    uptime_ms = kernel.GetTickCount64()
    return int(time.time() - uptime_ms / 1000)


def filesystem_name(root: Path) -> str:
    volume_name = ctypes.create_unicode_buffer(261)
    filesystem = ctypes.create_unicode_buffer(261)
    flags = ctypes.c_ulong()
    max_component = ctypes.c_ulong()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetVolumeInformationW.argtypes = (
        ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong), ctypes.c_wchar_p, ctypes.c_ulong,
    )
    kernel.GetVolumeInformationW.restype = ctypes.c_int
    ok = kernel.GetVolumeInformationW(
        str(root.anchor), volume_name, len(volume_name), None,
        ctypes.byref(max_component), ctypes.byref(flags), filesystem,
        len(filesystem),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    return filesystem.value


def write_evidence(root: Path, evidence: dict[str, object]) -> None:
    """Flush the evidence file and publish its name with Windows write-through."""
    temporary = root / f".{RECORD}-{uuid.uuid4().hex}.partial"
    with temporary.open("xb") as handle:
        handle.write((json.dumps(evidence, indent=2) + "\n").encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        with WindowsPromotionFileOps(root) as adapter:
            if adapter.sha256(RECORD) is None:
                adapter.copy_exclusive(temporary.name, RECORD)
                adapter.unlink(temporary.name)
            else:
                adapter.atomic_replace(temporary.name, RECORD)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: Path, name: str) -> None:
    db = Database(root / name, key=DUMMY_KEY, read_only=True)
    try:
        if not db.has_table("schema_migrations"):
            raise RuntimeError(f"{name} is not a Lightning database")
        inspect_schema(db)
        verify_connection(db.conn, encrypted=True)
    finally:
        db.close()


def activate(checkpoint_id: str, name: str) -> None:
    # This standalone drill has no app session to expose. Reverify the bytes;
    # successful return from recovery is the checkpoint acceptance evidence.
    if not checkpoint_id or name != LIVE:
        raise RuntimeError("Unexpected activation target")


def prepare(root: Path, target: PromotionPhase) -> int:
    if not root.drive or str(root).startswith("\\\\"):
        raise SystemExit("Choose a folder on a fixed local drive (not a network share).")
    if root.exists() and any(root.iterdir()):
        raise SystemExit("The drill folder must be new or empty; refusing to overwrite it.")
    root.mkdir(parents=True, exist_ok=True)

    home = build(root / LIVE, key=DUMMY_KEY)
    home.account_flows.open_account("Dummy start", "CASH", "2026-01-01", "100")
    home.db.close()
    staged = stage_database(root / LIVE, root, destination_key=DUMMY_KEY, source_key=DUMMY_KEY)
    candidate = root / CANDIDATE
    staged.path.replace(candidate)
    imported = build(candidate, key=DUMMY_KEY)
    imported.account_flows.open_account("Dummy restored", "CASH", "2026-01-02", "200")
    imported.db.close()

    store = SqlitePromotionJournalStore(root / CONTROL)
    store.initialize_accepted("dummy-base", digest(root / LIVE))
    files = WindowsPromotionFileOps(root)
    service = CandidatePromotionService(files, store)
    evidence = {
        "device": socket.gethostname(), "filesystem": filesystem_name(root),
        "armed_boot_epoch": boot_marker(), "target_phase": target.name,
        "live_sha256_before": digest(root / LIVE),
        "candidate_sha256": digest(root / CANDIDATE),
        "method": "ordinary Windows reboot; process exits immediately after requested durable phase",
    }
    write_evidence(root, evidence)

    def interrupt(method_name, phase):
        original = getattr(store, method_name)

        def wrapped(*args, **kwargs):
            result = original(*args, **kwargs)
            state = store.read_state()
            if state.journal and state.journal.phase is phase:
                # Leave the durable evidence exactly as a killed process would.
                os._exit(75 + int(phase))
            return result
        setattr(store, method_name, wrapped)

    if target is PromotionPhase.PREPARED:
        interrupt("prepare", target)
    elif target is PromotionPhase.PREVIOUS_PROTECTED:
        interrupt("advance", target)
    elif target is PromotionPhase.FILE_PUBLISHED:
        interrupt("advance", target)
    elif target is PromotionPhase.AUTHORITY_PUBLISHED:
        interrupt("commit_authority", target)

    print(f"Dummy encrypted profile ready; requested durable {target.name}. Reboot Windows, then run resume --root {root}", flush=True)
    with files:
        service.promote(
            operation_id="windows-reboot-drill", old_checkpoint_id="dummy-base",
            new_checkpoint_id="dummy-restored", live_name=LIVE,
            candidate_name=CANDIDATE, previous_name=PREVIOUS,
            operation_gate=Gate(), verify_database=lambda name: verify(root, name),
            activate=activate,
        )
    raise RuntimeError("Requested phase interruption did not occur")


def resume(root: Path) -> None:
    evidence_path = root / RECORD
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    now_boot = boot_marker()
    if now_boot <= evidence["armed_boot_epoch"] + 5:
        raise SystemExit("No Windows reboot detected. Reboot first, then run resume.")
    initial = SqlitePromotionJournalStore(root / CONTROL).read_state()
    initial_phase = initial.journal.phase.name if initial.journal else "none"
    files = WindowsPromotionFileOps(root)
    service = CandidatePromotionService(files, SqlitePromotionJournalStore(root / CONTROL))
    with files:
        result = service.recover(
            live_name=LIVE, operation_gate=Gate(),
            verify_database=lambda name: verify(root, name), activate=activate,
        )
        state = service.store.read_state()
        accepted = state.accepted
        live_hash = files.sha256(LIVE)
        previous_hash = files.sha256(PREVIOUS)
    if (result.checkpoint_id != "dummy-restored" or accepted is None
            or accepted.sha256 != live_hash or live_hash != evidence["candidate_sha256"]
            or previous_hash != evidence["live_sha256_before"]
            or state.journal is None or state.journal.phase is not PromotionPhase.ACTIVATED):
        raise SystemExit("Recovery did not reach the verified checkpoint; evidence is retained and profile remains blocked.")
    verify(root, LIVE)
    evidence.update({
        "resumed_boot_epoch": now_boot, "phase_seen_after_reboot": initial_phase,
        "outcome": "PASS: encrypted dummy checkpoint verified; retained previous checkpoint matches; journal P5",
        "accepted_sha256": accepted.sha256,
    })
    write_evidence(root, evidence)
    print(json.dumps(evidence, indent=2))


def require_windows() -> None:
    if os.name != "nt":
        raise SystemExit("This drill requires Windows and a fixed local drive.")


def main() -> None:
    require_windows()
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    arm = commands.add_parser("prepare", help="create dummy encrypted data and stop at a durable phase")
    arm.add_argument("--root", required=True, type=Path)
    arm.add_argument("--phase", required=True, choices=("P1", "P2", "P3", "P4"))
    reboot = commands.add_parser("resume", help="recover and record evidence after Windows reboot")
    reboot.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        phase = {
            "P1": PromotionPhase.PREPARED,
            "P2": PromotionPhase.PREVIOUS_PROTECTED,
            "P3": PromotionPhase.FILE_PUBLISHED,
            "P4": PromotionPhase.AUTHORITY_PUBLISHED,
        }[args.phase]
        prepare(args.root.resolve(), phase)
    else:
        resume(args.root.resolve())


if __name__ == "__main__":
    main()
