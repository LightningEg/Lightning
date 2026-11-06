---
title: Phone data must survive every app update and reinstall
type: bug
look: technical
severity: high
pillar: protect
size: L
status: new
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

## 2AI1 Pin the phone's identity, built 2026-11-05 · S

`tests/test_phone_identity_frozen.py` pins the one application ID and the signing certificate; `phone_build.py`
and `android_test_key.py` now say that a new key deletes people's data and needs a signing lineage.

## 2AI2 Open a profile file on the phone, built 2026-11-06 · M

Owner chose one `.lightning` file (2026-11-06). The PC's Profile settings has "Save a profile file"; the profile
list has "Open a profile file" (the phone's WebView file chooser, no new native code). The file is a zip of
`manifest.json`, `profile.db` (a verified encrypted copy) and `keys.json` (the password-wrapped key);
`lightning/runtime/profile_file.py` checks shape, hashes, password and database before anything is written, and
refuses a profile already on the device. Tests: `tests/test_profile_file.py`. Left: the owner opens a file on the
real phone (joins the held native checks).

## 2AI3 A copy outside the app · M

Once, the phone asks for a folder (`ACTION_OPEN_DOCUMENT_TREE`, persisted); after each day's first change it
writes the encrypted backup there and keeps the last three. An uninstall then leaves that copy behind, and 2AI2
opens it. Settings shows when the last copy was written.

## 2AI4 The PC can always send its copy to a fresh phone · M

When device editing is on and the phone has lost the home, the PC offers "Send this book to a new phone" from its
newest verified copy, starting a new history as 4A section 7 describes (lost-home recovery, cutoff shown).

Done when: updating, reinstalling or replacing the phone never leaves a person without their book.
