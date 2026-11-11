---
title: Ordinary-PC acceptance: recovery and faults, legacy import, native file pickers, unresolved-evidence repair
type: tech
pillar: protect
size: L
model: opus
status: parked
post: no
created: 2026-10-19
by: Claude
---

## Report
What stands between the paired apps beta (1.0.0-beta.1) and real money (AGENTS.md §4): ordinary-PC recovery and fault acceptance, importing data from the legacy mode (`python -m lightning`), native file pickers, unresolved-evidence repair, and native Windows/Android delivery of reminders (Overview, smarter workflows 2026-10-15).

## What is left (2026-11-10)

2C2-2C6 were built on 2026-11-10 (Claude, one pull request at the owner's choice):
- **Legacy import (2C2):** Profiles shows "Bring in your old Lightning data" when an old `data/lightning.db` is found;
  it becomes a new encrypted profile (`runtime/session.py` `check_legacy_database`, `confirm`; `tests/test_legacy_import.py`).
- **Restore from anywhere (2C3):** "Choose a backup file…" opens the Windows Open dialog from Python
  (`runtime/file_picker.py`, `desktop/window.py` `_pick_backup`, `POST /profiles/restore/pick`; `tests/test_restore_picker.py`).
- **Repair (2C4):** "Restore needs checking" lists the kept files and goes back to the copy from before the restore
  (`runtime/restore.py` `go_back_before_restore`, `/profiles/restore/repair`; `tests/test_restore_go_back.py`).
- **Reminders (2C5):** `tests/test_native_reminders.py`. With the app closed stays [NF-3AU](../3-polish-and-arabic/NF-3AU-reminders-when-the-app-is-closed.md).
- **Sheet (2C6):** below. Left: the owner runs it once (2C1).

## Decided

- 2026-11-08, owner (2C7): (a) "Go back to the copy from before the restore" after the password, through the normal restore path; every other file stays as evidence.

## Owner sheet

One sitting on an ordinary Windows PC with a **dummy** profile, never a real one. Write *pass* or what happened in the
last column; a failed row becomes a bug item.

| # | Do | Safe result | Source | Result |
|---|---|---|---|---|
| 1 | Unzip the release ZIP into a new folder and start `Lightning.exe`; repeat on the PC that once failed at window startup | The profile chooser opens; nothing asks for Python | Architecture › Desktop app | |
| 2 | `python tools/promotion_drill.py prepare --root <empty folder> --phase P1`, reboot, `resume --root <same>`; repeat for P2, P3, P4 | Each resume reports the promoted database and no lost data | `tools/promotion_drill.py` (2B) | |
| 3 | Start a restore (Profiles › a backup › Restore backup), turn the PC off with the power button while it runs, start again, unlock | "Check interrupted restore →" leads to "Check and resume"; the profile opens with the backup's data | Architecture › Restore (IT-2A) | |
| 4 | Make a dummy plaintext database from a source checkout (`python -c "from lightning.bootstrap import build; build('data/lightning.db')"`), copy it to `data\lightning.db` in the folder `Lightning.exe` starts from, open Profiles | "Bring in your old Lightning data" appears; the new profile has the same accounts and transactions; the old file is unchanged | 2C2 | |
| 5 | Use each file field once: Import, Bank statement, Broker import, Exports › Import, Exports › Starter, Investments › Prices; then Settings › Save a copy; then Profiles › Restore a backup file… › Choose a backup file… from a USB stick | Each Windows dialog opens, the file goes in (or is refused with a message), the saved copy lands in Downloads, the USB backup restores | 2C3 | |
| 6 | After row 3, if resume says it is blocked: "Resume cannot finish? Go back to the copy from before the restore →", password, confirm | The profile opens with its data from before the restore; a `restore-evidence-…` folder holds the other files | 2C4 | |
| 7 | Turn on reminders with a bill due today and keep the app open for a minute; click the balloon | One Windows balloon; clicking opens that bill's page | 2C5 | |
| 8 | The Windows rows of the physical matrix | As each row says | [pairing acceptance](../4-edit-journal-and-devices/r11-pairing-hardening/evidence/acceptance.md) | |

## 2C1 Owner: run the ordinary-PC sheet · owner
Needs 2C2, 2C3, 2C4, 2C5 and 2C6 merged first. Held for the end-to-end check (Overview §9): the owner runs the
`## Owner sheet` once on an ordinary PC with dummy data and reports each row. A failed row becomes a bug item; when
all pass, `ai/ARCHITECTURE.md` "Open before a release" drops these parts and milestone 2's *done when* can be checked.
