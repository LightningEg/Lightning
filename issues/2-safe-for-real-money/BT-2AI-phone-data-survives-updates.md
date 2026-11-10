---
title: Phone data must survive every app update and reinstall
type: bug
look: technical
severity: high
pillar: protect
size: L
model: opus
status: blocked
blocked_by: 4A4 (step 2AI4) and the owner phone check (2AI6)
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
2AI2 is built too: the profile chooser (phone and PC) has "Open a profile file" (`/profiles/open-file`,
`lightning/runtime/profile_screens.py`), which takes a `.lightning` file and its password, adds the book as a new
profile and opens it; Arabic included. On Android the WebView's `onShowFileChooser` (`MainActivity.java`, ~222) shows
the system picker. 2AI3 is built: phone Settings › Backup has "Keep a copy outside the app" (`lightning/runtime/outside_copy.py`,
`BackupFolderBridge.java`): a folder chosen once gets a profile file a day and keeps the newest three. The manifest still
has `allowBackup="false"` (owner decision, unchanged). Saving by hand goes through the system "Save to" screen
(`FileBridge.java`, files up to 64 MB: `phone_files.MAX_FILE_BYTES`). Left: 2AI4 (waits on 4A4) and the owner's 2AI6.
Known limits: the request guard holds an upload in memory before the route sees it (Architecture › Profile file); a
profile whose name is not ASCII is offered as `Lightning-profile-<date>.lightning`; a journal review copy saved by an
older schema is refused until its home saves a new one.

Note for the owner's own lost book: it is still inside the old app "Lightning Test" (`org.lightning.app.test`) as
long as that app is not uninstalled. Once 2AI5 ships in a build of the old ID, that app can save a profile file.

## How to work on this item

One step is one pull request. Read only the files a step names; Android and profile data are opus work. Tests:
`python -m pytest tests/test_profile_file.py tests/test_phone_identity_frozen.py -q` plus the step's own; native
Android behaviour is checked by the owner at the end (2AI6), not step by step. Dummy profiles only. Delete the
step's heading in the same commit.

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
