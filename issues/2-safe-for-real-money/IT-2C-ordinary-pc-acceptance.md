---
title: Ordinary-PC acceptance: recovery and faults, legacy import, native file pickers, unresolved-evidence repair
type: tech
pillar: protect
size: L
model: opus
status: ready
post: no
created: 2026-10-19
by: Claude
---

## Report
What stands between the paired apps beta (1.0.0-beta.1) and real money (AGENTS.md §4): ordinary-PC recovery and fault acceptance, importing data from the legacy mode (`python -m lightning`), native file pickers, unresolved-evidence repair, and native Windows/Android delivery of reminders (Overview, smarter workflows 2026-10-15).

## What is left (2026-11-08)

Checked against the code on 2026-11-08 (Claude). None of the five parts is finished, but some pieces exist:
- **Recovery and faults:** `tools/promotion_drill.py` (Windows reboot drill, held as 2B in Overview §9), restore and
  resume (`runtime/restore.py`, IT-2A), the pairing fault kit (`tools/pairing_acceptance.py`,
  `issues/4-edit-journal-and-devices/r11-pairing-hardening/evidence/acceptance.md`). No single sheet brings them together.
- **Legacy import:** not built (`runtime/session.py:347` says "Explicit import is not available yet"). The parts exist:
  `database/staging.py` `stage_database(source, folder, destination_key=key)` with no `source_key` reads plaintext
  and writes an encrypted copy; `runtime/paths.py:412` `legacy_database_candidates` finds old `data/lightning.db`
  files without opening them. Only people who ran `python -m lightning` from source before OW-2AB have such a file.
- **File pickers:** every `<input type="file">` (6 templates: `import.html`, `bank_import_upload.html`,
  `broker_import.html`, `exports/import.html`, `exports/starter.html`, `investments/prices.html`) and the "Save a copy"
  download (`/backup/latest`, `webview.settings["ALLOW_DOWNLOADS"]` in `desktop/window.py`) rely on WebView2's own
  dialogs; none was run on an ordinary PC. Restore only takes a backup already in the profile's `backups/` folder
  (`runtime/restore.py` ~388), so a backup on a USB stick cannot be restored.
- **Unresolved evidence:** when a restore or its resume cannot prove the next step, the profile stays locked "with
  evidence preserved" (`runtime/restore.py` ~641-692, `database/promotion.py` `PromotionBlocked`); the person has no
  way forward but to leave it.
- **Notifications:** built while the app runs (`desktop/window.py` `_native_reminder_loop`,
  `ReminderNotifications.java`); with the app closed is NF-3AU. Only `_safe_reminder_href` is unit-tested.

The owner runs native checks only end to end (NOW.md, Overview §9), so the AI builds and prepares everything first
(2C2-2C6), and the owner runs one sheet once (2C1).

## Decided

- 2026-11-08, owner (2C7): (a) "Go back to the copy from before the restore" after the password, through the normal restore path; every other file stays as evidence.

## How to work on this item

One step is one pull request. Read only the files a step names; dummy profiles only, never a real one. Run the
step's test, then `python -m pytest tests/test_mohab_year.py -q` for visible changes; new text gets Arabic in
`lightning/ui/i18n.py` `ARABIC_UI` (or `i18n_system.py` for profile-screen messages, where the others are). Delete the
step's heading in the same commit; update `ai/ARCHITECTURE.md` "Open before a release" (~582) when a part is done.

## 2C2 Legacy import · M · opus
Files: `lightning/runtime/session.py` (`PendingProfile` ~186, `prepare` ~252, `confirm` ~274, the refusal ~347),
`lightning/database/staging.py` (`stage_database`), `lightning/runtime/paths.py` (`legacy_database_candidates` ~412),
`lightning/runtime/profile_screens.py` (`/profiles` ~86, `/profiles/new` ~124-146), `lightning/ui/templates/profiles.html`
(`choose` and `setup` modes), new `tests/test_legacy_import.py`.
Do: `PendingProfile` gains `legacy_source: Path | None`. `prepare(..., legacy_source=None)` checks the file starts
with `b"SQLite format 3\x00"` and has `schema_migrations`. In `confirm`, when `legacy_source` is set, replace the fresh
`build(candidate, ...)` with `stage_database(legacy_source, paths.data_dir, destination_key=pending.key)` renamed to the
`.partial` candidate, then `build()` it (migrations run on the copy), fsync and `publish_new` as today; keep the old
database's own currency (skip `register`/`set_profile_currency`). The source is opened read only and never changed.
The chooser shows "Bring in your old Lightning data" when `legacy_database_candidates(project_root=<repo root>,
cwd=Path.cwd())` finds files, linking `/profiles/new?legacy=<index>` (an index into that list, never a path from
the request). The refusal at ~347 points to that link.
Done when: `tests/test_legacy_import.py` builds a plaintext database with `build(path)` and a few transactions,
imports it, and asserts: the new file is encrypted (first 16 bytes are not the SQLite header), account balances and
transaction count are equal, the source's SHA-256 is unchanged, a non-Lightning SQLite file and a `?legacy=9` index
are refused, and a failed import leaves no published profile. `python -m pytest tests/test_legacy_import.py tests/test_legacy_launcher.py -q`.

## 2C3 Restore a backup from anywhere (Windows Open dialog) · M · opus
Files: `lightning/desktop/window.py` (`run_window` ~251; `create_window(..., js_api=None)` ~397),
`lightning/runtime/app.py` (`/profiles/restore` ~365-398), `lightning/runtime/restore.py` (`restore_backup` ~368-395),
`lightning/database/backup.py` (`list_backups` naming), `lightning/ui/templates/profiles.html` (`restore` mode ~196),
`tests/test_desktop_window.py`, `tests/test_database_promotion.py` (restore fixtures).
Do: keep `js_api=None` (no page script reaches native code). Add `POST /profiles/restore/pick?db=` which, only when a
desktop window registered a picker (a callable the window sets on app state at start; absent in browser mode and on
the phone, where the route answers 404), opens `window.create_file_dialog(webview.OPEN_DIALOG,
file_types=("Lightning backup (*.db)",))` from Python, copies the chosen file into that profile's `backups/` under a
name `list_backups` accepts (suffix `_picked`), and redirects to the existing `/profiles/restore?db=&backup=`; the
restore then verifies it with the profile's key as now. A file that is not this profile's backup fails there with the
existing message, and the copy is removed. The restore page shows "Choose a backup file…" beside the list on Windows.
Done when: a test with a fake picker returns a dummy profile's backup from a temp folder outside the profile and the
restore completes; a picker returning another profile's backup is refused and leaves no copy; with no picker the
route is 404. `python -m pytest tests/test_desktop_window.py tests/test_database_promotion.py -q`.

## 2C4 Unresolved-evidence repair · M · opus
Needs 2C7 agreed first.
Verify first: IT-2A (2A3 deterministic repair) may already offer a way out; read `runtime/restore.py`
`resume_interrupted_restore` (~545-692) and the `resume-restore` screen before building.
Files: `lightning/runtime/restore.py`, `lightning/database/promotion.py` (`PromotionBlocked` ~775), `lightning/runtime/app.py`
(`/profiles/restore/resume` ~400-425), `lightning/ui/templates/profiles.html` (`resume-restore` mode ~211),
`tests/test_database_promotion.py`.
Do: what 2C7 chose. For (a): a screen "Restore needs checking" listing the kept files with their check result, and
"Go back to the copy from before the restore" that, after the password, restores the pre-restore snapshot recorded in
the restore manifest (`RestoreManifest`) through `restore_backup`, refusing if its hash differs from the manifest. For
(b): `GET /profiles/restore/diagnostic?db=` returns JSON of file names, sizes, SHA-256 and the last phase, with no
database bytes, key material or profile name.
Done when: a fault test interrupts a restore so that resume raises `PromotionBlocked`, then the chosen way out leaves
a profile that unlocks with the pre-restore data (a) and/or a diagnostic with no secret (b, asserted by searching it
for the password, key and name). `python -m pytest tests/test_database_promotion.py -q`.

## 2C5 Native reminder delivery: test what runs on Windows · S · sonnet
Verify first: [NF-3AU](../3-polish-and-arabic/NF-3AU-reminders-when-the-app-is-closed.md) covers the app-closed
case; do not build that here.
Files: `lightning/desktop/window.py` (`_read_reminder_prefs`, `_write_reminder_prefs`, `_native_reminder_loop` ~37-110),
new `tests/test_native_reminders.py`.
Do: tests only, no product change. (1) prefs: a missing, corrupt or non-dict file reads as `{}`; write then read
round-trips. (2) the loop with a fake `window` whose `evaluate_js` returns a JSON payload, `native_state={"icon": object()}`,
a fake `window.native` with `BeginInvoke`, and `sys.modules["System"]` monkeypatched to a module with `Action = lambda f: f`;
`closed` is set by the fake after the first poll. Assert: one balloon for the first valid item; none when `enabled`
is false; items with a bad id, an outside href or an empty label are skipped; an id already seen today is not shown
again (prefs path monkeypatched to `tmp_path`).
Done when: `python -m pytest tests/test_native_reminders.py tests/test_workflow_views_review.py -q` passes on Linux.

## 2C6 One ordinary-PC acceptance sheet · S · sonnet
Files: this item (append a section `## Owner sheet`), `tools/promotion_drill.py` (header), `ai/ARCHITECTURE.md`
"Open before a release" (~582) and "Updating", `issues/4-edit-journal-and-devices/r11-pairing-hardening/evidence/acceptance.md`
(physical matrix), `ai/PROJECT_OVERVIEW.md` §9.
Do: one table the owner can run in one sitting on an ordinary Windows PC with a dummy profile, each row with the exact
action, the expected safe result and a blank result cell: (1) a clean install from the release ZIP, on the PC that
once failed at window startup too; (2) `tools/promotion_drill.py` phases P1-P4 across a reboot (2B); (3) a restore
interrupted by a reboot, then resumed (2A5); (4) legacy import of a dummy plaintext database (2C2); (5) each of the
six file fields above, "Save a copy", and "Choose a backup file…" (2C3); (6) the repair screen (2C4); (7) a reminder
balloon while the app is open, clicked through to its page (2C5); (8) the Windows rows of the pairing matrix. Link
each row to its source; copy no steps that already live elsewhere (link them).
Done when: `python -m pytest tests/test_docs_structure.py -q` passes and every row names one command or screen.

## 2C1 Owner: run the ordinary-PC sheet · owner
Needs 2C2, 2C3, 2C4, 2C5 and 2C6 merged first. Held for the end-to-end check (Overview §9): the owner runs the
`## Owner sheet` once on an ordinary PC with dummy data and reports each row. A failed row becomes a bug item; when
all pass, `ai/ARCHITECTURE.md` "Open before a release" drops these parts and milestone 2's *done when* can be checked.
