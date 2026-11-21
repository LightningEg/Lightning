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

**Built:** 2A1 durable intent before the source copy (#713: `RestoreIntent`, `lightning/runtime/restore.py`, `tests/test_profile_session.py`); 2A2 durable moves and discards, write-through on Windows (#715: `_durable_move`/`_durable_discard`, `move_write_through` in `lightning/database/promotion_windows.py`, `tests/test_restore_durable_moves.py`); 2A3 one deterministic repair (#714: `repair_interrupted_restore`, `tests/test_restore_repair.py`). Left: the screens and docs (2A4) and the owner's reboot drill (2A5).

## 2A4 Restore screens and docs · M
Codex owns the restore UI and the Architecture text; the reboot drill joins the owner's held checks.

## 2A5 Reboot drill on an ordinary PC · owner
Power-loss and reboot during a restore, on the owner's PC.
