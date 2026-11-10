---
title: Phone data must survive every app update and reinstall
type: bug
look: technical
severity: high
pillar: protect
size: L
model: opus
status: building
created: 2026-11-05
by: Claude Opus 5.5
skills: feedback-review
app_version: 2.0.3
commit: 75d63ae
repo: app
---

## Report

The owner updated the phone to 2.0.x and the book was gone, and the PC had no way to send it back
([feedback](../../feedback/2026-11-05-csv-import-and-phone-update.md)).

## Investigation

Claude Opus 5.5, feedback-review, 2026-11-05.

- **Cause:** 2.0.0 (IV-3AX, a412705) changed the application ID from `org.lightning.app.test` ("Lightning Test")
  to `org.lightning.app`. Android installed it as a second, empty app; the book stayed in the old one.
- **Why nothing caught it:** the phone keeps every profile in app-private storage (`getFilesDir()`,
  `MainActivity.java`), the manifest sets `allowBackup="false"`, and a test that pinned the ID was edited with it.
  A changed signing key has the same effect: the update is refused and the uninstall deletes the data. The build's
  own error message advised pinning a new key.
- **No way back from the PC:** "Move to your phone" (`profiles.html`) is hidden once device editing is on, and the
  phone's Restore lists only backups already inside the app. Nothing on the phone opens a file the person brings.

## What is left (2026-11-09)

Built: 2AI1 (c5396702, #352: `tests/test_phone_identity_frozen.py` pins the application ID and signing certificate) and
2AI5 (`lightning/runtime/profile_file.py`, `tests/test_profile_file.py`; Architecture › Profile file): one
`<name>-<date>.lightning` file holds the key file and a fresh encrypted snapshot, `read_profile_file(path, password, root)`
publishes it as a new profile (a journal profile as a read-only review copy), and Settings › Save a copy sends it.
Nothing yet lets a person bring such a file in (2AI2) or keeps one outside the app (2AI3): no
`ACTION_OPEN_DOCUMENT`/`ACTION_OPEN_DOCUMENT_TREE` in `android/`, and the manifest still has `allowBackup="false"`.
The WebView already opens the system picker for any `<input type="file">` (`MainActivity.java` `onShowFileChooser`,
~222) and saves through the system "Save to" screen (`FileBridge.java`, files up to 64 MB: `phone_files.MAX_FILE_BYTES`).
Known limits for 2AI2: `profile_file`'s error messages are English only (add them to `lightning/ui/i18n.py`); a profile
whose name is not ASCII is offered as `Lightning-profile-<date>.lightning`; a journal review copy saved by an older
schema is refused until its home saves a new one.

Note for the owner's own lost book: it is still inside the old app "Lightning Test" (`org.lightning.app.test`) as
long as that app is not uninstalled. Once 2AI5 ships in a build of the old ID, that app can save a profile file.

## How to work on this item

One step is one pull request. Read only the files a step names; Android and profile data are opus work. Tests:
`python -m pytest tests/test_profile_file.py tests/test_phone_identity_frozen.py -q` plus the step's own; native
Android behaviour is checked by the owner at the end (2AI6), not step by step. Dummy profiles only. Delete the
step's heading in the same commit.

## 2AI2 Open a profile file on the phone · M · opus
Files: `lightning/ui/templates/profiles.html` (the `choose` mode), `lightning/runtime/profile_screens.py` (routes
~86-160), `lightning/runtime/app.py` (`_body_limit`, `_form_file_limit` ~44-56: only listed routes accept a file),
`lightning/runtime/http.py` (`configure_memory_only_import_uploads`), `lightning/ui/i18n.py`, `tests/test_profile_file.py`.
Do: on the profile chooser (phone and PC), a link "Open a profile file" to `GET /profiles/open-file`: a form with
`<input type="file" name="profile" accept=".lightning">` and the profile password. `POST /profiles/open-file` is
added to the file-accepting routes with the 256 MB cap; the upload is spooled to a private temporary file in the
app's data folder (not memory), passed to `read_profile_file`, and deleted after. Works with no network and no
pairing; on Android the existing `onShowFileChooser` shows the system picker (USB, Drive, WhatsApp files).
Done when: an HTTP test posts a profile file made by `write_profile_file` and then unlocks the new profile with its
password; a wrong password leaves no new folder; any other route still rejects a file part
(`python -m pytest tests/test_profile_file.py -q`).

## 2AI3 A copy outside the app · M · opus
Files: `android/app/src/main/java/org/lightning/app/MainActivity.java`, a new `BackupFolderBridge.java` beside
`FileBridge.java`, `android/app/src/main/python/lightning_android.py` (adapter as for `FileBridge`, ~87-115),
the page that links `/backup/latest` (`grep -rln "backup/latest" lightning/ui/templates`), `tests/test_android_shell.py`.
Do: next to "Save a copy", "Keep a copy outside the app" (phone only): once, `ACTION_OPEN_DOCUMENT_TREE`, and
`takePersistableUriPermission` on the chosen folder (URI kept in app settings, no storage permission). After the
day's first backup (made when a profile opens: `lightning/bootstrap.py` ~213, `backed_up_today`), write a profile file (2AI5) there through the
DocumentsContract API and keep the newest three, deleting older `*.lightning` files Lightning wrote. Settings shows
"Last copy: <date>" or why it failed (folder gone, permission revoked). An uninstall leaves the folder; 2AI2 opens it.
Done when: a Python test of the adapter's choice of what to write and what to prune (fake bridge), and
`tests/test_android_shell.py` asserts the bridge class and the persisted-permission call exist; the Android build
workflow passes (run `android-app.yml` by hand once, AGENTS §2).

## 2AI4 The PC can always send its copy to a fresh phone · M · opus
Needs 4A4 merged first.
Files: `lightning/ui/templates/profiles.html` (the `devices` and `manage` modes; "Move to your phone" ~368),
`lightning/runtime/app.py` (`/profiles/move` ~704, `/profiles/devices*` ~481-560),
`issues/4-edit-journal-and-devices/NF-4A-edit-journal.md` §7 "Lost-home recovery and stale devices".
Verify first: once device editing is on, is "Move to your phone" still hidden, and is there still no PC path to a
new phone? If 4A4 built lost-home recovery with a PC entry, this step is only the profile-file route below.
Do: when device editing is on and the phone home is lost, the PC offers "Send this book to a new phone": until 4A4's
recovery exists, it saves a profile file (2AI5) from the PC's newest verified copy, shown with its last confirmed
date ("edits after <date> made only on the lost phone are not in it"), which the new phone opens with 2AI2 as a new
history; after 4A4, it starts 4A §7 recovery instead.
Done when: a test with a dummy journal profile: the PC page shows the offer only when the home is marked lost, and
the saved file opens on a fresh root as a review copy with the cutoff shown.

## 2AI6 Owner: the phone survives an update and a reinstall · owner
Held for the end-to-end check (Overview §9): on a real phone, with a dummy profile, (1) install the current release,
then the next build over it: the book is there; (2) with 2AI3 on, uninstall and reinstall: Open a profile file
(2AI2) brings the book back from the outside folder; (3) save a profile file on the PC and open it on a second phone.
Done when: updating, reinstalling or replacing the phone never leaves a person without their book.
