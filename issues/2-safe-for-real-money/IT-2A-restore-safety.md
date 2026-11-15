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

## 2A3 Explicit deterministic repair · L
After an interruption, one repair path finishes or undoes the restore the same way every time.

**Done when:** the state on disk alone picks the repair. A restore that published nothing is undone; one whose journal reached P1 is finished forward; anything else stays locked with its evidence (go back, IT-2C4, stays the owner's way out).
- **Intent only** (2A1: no manifest): cleared at unlock and before the next restore. The source copy is deleted when the chosen backup still matches the intent's hash, else moved to `restore-evidence-<id>/`; then the intent goes.
- **PENDING manifest, no journal yet** (no file, or a store with no journal): undone when the live file still has the manifest's old hash. Record, store, candidate, intent and source copy move to `restore-evidence-<id>/`; the live file is untouched. Today resume refuses this and only go back (a full second restore) gets out.
- **PENDING manifest with a journal:** finished forward, as resume does now.
- The resume screen calls this one repair and says which of the two happened. Tests kill the process at each boundary and repeat the repair to show it lands the same way.

## 2A4 Restore screens and docs · M
Codex owns the restore UI and the Architecture text; the reboot drill joins the owner's held checks.

## 2A5 Reboot drill on an ordinary PC · owner
Power-loss and reboot during a restore, on the owner's PC.
