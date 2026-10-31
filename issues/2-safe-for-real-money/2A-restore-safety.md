---
title: Restore safety: durable intent, source-copy manifest, Windows marker publication, deterministic repair
type: tech
pillar: protect
size: L
status: building
created: 2026-10-19
by: Codex
---

## Report
Codex task 03a, built by Luna for Codex; Codex reviews it and owns the restore UI and docs. Claimed in `NOW.md`.

**Read:** the claim in [NOW.md](../../NOW.md); Architecture › Desktop app and encrypted profiles.

## 2A1 Durable intent and source-copy manifest · L
Luna's claim in NOW.md. A restore records what it will do before it does it, and what it copied from.

## 2A2 Windows marker publication · L
The restore marker is published atomically on Windows (`database/promotion_windows.py`).

## 2A3 Explicit deterministic repair · L
After an interruption, one repair path finishes or undoes the restore the same way every time.

## 2A4 Restore screens and docs · M
Codex owns the restore UI and the Architecture text; the reboot drill joins the owner's held checks.

## 2A5 Reboot drill on an ordinary PC · owner
Power-loss and reboot during a restore, on the owner's PC.
