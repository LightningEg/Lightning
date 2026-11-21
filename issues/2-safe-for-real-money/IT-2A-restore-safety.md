---
title: Restore safety: durable intent, source-copy manifest, Windows marker publication, deterministic repair
type: tech
pillar: protect
size: L
model: opus
status: parked
created: 2026-10-19
by: Codex
---

## Report
Codex task 03a, built by Luna for Codex; Codex reviews it and owns the restore UI and docs. Claimed in `NOW.md`.

**Read:** the claim in [NOW.md](../../NOW.md); Architecture › Desktop app and encrypted profiles.

## 2A1 Durable intent and source-copy manifest · L
A restore records what it will do before it does it, and what it copied from.

Built before (Luna, 2026-10-05): the PENDING manifest binds the source, its protected copy, the pre-restore snapshot and the candidate to the promotion journal before P1; unlock checks every retained hash. **Gap:** the protected source copy (`backups/.lightning-restore-source-<id>.db`) is written *before* any record exists. A kill or power cut in that window leaves a copy no record explains, and unlock then refuses the profile for good: there is no PENDING manifest to resume or go back from.

**Done when:** a durable intent record (`.lightning-restore-<id>.intent`: operation, profile, live file and hash, source name and hash, source-copy name) is fsynced before the pre-restore snapshot and the source copy; unlock treats an intent with no manifest and no journal as a restore that stopped before it published anything, so the profile opens; an intent beside a manifest is ignored; a malformed or unsafe intent locks; go back moves the intent with the other evidence; tests kill the process at each new step. Clearing the leftover copy is 2A3's repair.

**Built (#713):** `RestoreIntent` in `lightning/runtime/restore.py`; tests in `tests/test_profile_session.py` (`*intent*`, `test_kill_*`). Left for 2A3: clearing an unpublished intent and its copy.

## 2A2 Windows marker publication · L
The restore marker is published atomically on Windows (`database/promotion_windows.py`).

Built before: the manifest and intent are published through `WindowsPromotionFileOps.copy_exclusive`/`atomic_replace` (`MoveFileExW` with `MOVEFILE_WRITE_THROUGH`). **Gap:** every other restore-control step on Windows uses `os.replace`/`unlink`, and `_fsync_directory` is a no-op there, so a power cut can keep a later step and lose an earlier one. Where that matters: a failed restore and unlock's clean-up delete the source copy and then the intent (losing only the first leaves a copy with no record: the 2A1 lock again); the 2A3 undo and go back move the record last, after the files it explains.

**Done when:** restore moves and discards go through one durable step: on Windows a `MOVEFILE_WRITE_THROUGH` move (a discard is a write-through rename to a `.lightning-discard-*` name, then a delete; leftovers are swept at unlock); on POSIX a rename followed by an fsync of both folders. The copy is gone durably before its intent, and the record moves after its files, on both. Tests pin the order on Linux; the adapter's move runs in the Windows job.

**Built (#715):** `_durable_move`/`_durable_discard` in `lightning/runtime/restore.py`, `move_write_through` in `lightning/database/promotion_windows.py`; tests in `tests/test_restore_durable_moves.py` and `tests/test_database_promotion_windows.py`, both added to the Windows job.

## 2A3 Explicit deterministic repair · L
After an interruption, one repair path finishes or undoes the restore the same way every time.

**Done when:** the state on disk alone picks the repair. A restore that published nothing is undone; one whose journal reached P1 is finished forward; anything else stays locked with its evidence (go back, IT-2C4, stays the owner's way out).
- **Intent only** (2A1: no manifest): cleared at unlock and before the next restore. The source copy is deleted when the chosen backup still matches the intent's hash, else moved to `restore-evidence-<id>/`; then the intent goes.
- **PENDING manifest, no journal yet** (no file, or a store with no journal): undone when the live file still has the manifest's old hash. Record, store, candidate, intent and source copy move to `restore-evidence-<id>/`; the live file is untouched. Today resume refuses this and only go back (a full second restore) gets out.
- **PENDING manifest with a journal:** finished forward, as resume does now.
- The resume screen calls this one repair and says which of the two happened. Tests kill the process at each boundary and repeat the repair to show it lands the same way.

**Built (#714):** `repair_interrupted_restore` and `_clear_unpublished` in `lightning/runtime/restore.py`; tests in `tests/test_restore_repair.py`.

## 2A4 Restore screens and docs · M
Codex owns the restore UI and the Architecture text; the reboot drill joins the owner's held checks.

## 2A5 Reboot drill on an ordinary PC · owner
Power-loss and reboot during a restore, on the owner's PC.
