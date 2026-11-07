---
title: In-app updates on Windows
type: feature
pillar: everywhere
size: L
status: new
created: 2026-10-19
by: Claude
---

## Report
Today a Windows user updates by hand: close the app, extract the new ZIP into a fresh folder, launch
([Architecture › Build and release](../../ai/ARCHITECTURE.md#desktop-app-and-encrypted-profiles), "Updating").
Wanted: a **Check for updates** button in Settings that finds the newest release in `LightningEg/Lightning-downloads`,
proves it came from us, installs it with one restart, and puts the old version back by itself if the new one fails
to start. Profiles (Documents/Lightning) and borrowed copies (`%LOCALAPPDATA%\Lightning\borrowed`) are never touched.
Android updates come from Google Play or the APK; this item is Windows only.

## Owner decisions (2026-11-06)
1. **Trust: our own Ed25519 key.** CI signs a small `UPDATE.json`; the app pins the public key. The ZIP stays
   unsigned for Windows (no Authenticode). HTTPS and `SHA256SUMS` alone are not enough.
   **Key, for now: the store key `store-2026-1`** (owner, 2026-11-06: "same key now, split later"). Its private JWK
   also sits in Supabase secrets, so a Supabase leak could forge updates; therefore every signature is over
   `b"lightning-update-v1:" + UPDATE.json bytes` (a licence can never pass as an update), and **before the first
   release that carries the updater** the owner makes a separate update key, both public keys ship in
   `update_keys.json`, and CI signs with the new one. Track that switch in 9B5's checklist.
   9B1 is built (signing in CI, `update_manifest.verify`; ARCHITECTURE › Build and release); the owner's part is done:
   `UPDATE_SIGNING_KEY` (store-2026-1) is set in `production-release`. 9B2 is built in `lightning/desktop/update.py` (`check`, `download`, `stage`; its `verify_manifest` mirrors `packaging/update_manifest.py`, a test keeps them equal).
2. **Check only on click.** Lightning never contacts GitHub for updates unless the person presses the button.
   No automatic or scheduled check, no setting for one.
3. **Rollback: automatic, plus one kept copy.** If the new version does not reach its profile chooser, the helper
   restores the old folder by itself. The previous folder is kept until the next update so it can be opened by hand.
   No "Go back" button.

## Rules every step keeps
- No financial data, profile name or ID leaves the PC; the only requests are GitHub's release API and the asset
  downloads, with `User-Agent: Lightning/<version>`.
- Never ask people to turn off a Windows protection. If the install folder is not writable (e.g. Program Files),
  say so and offer the download page; do not ask for administrator rights.
- Refuse to install while any borrowed profile is in `BORROW_PREPARED`, `BORROWING`, `SEALED`, `RETURNING` or
  `NEEDS_REPAIR` (`runtime/devices.py` `Devices.borrowed()`, states in `sync/state.py`), or while a journal
  move-home is unfinished (`runtime/journal_move.py` `JournalMoveRuntime`). `PREFETCHED`, `HANDED_BACK` and `ABORTED` are fine.
  Reason: [NF-4B › Compatibility and updates](../4-edit-journal-and-devices/NF-4B-multiple-devices.md#13-compatibility-and-updates).
- Never install an older or equal version. The manifest's version must be greater than `DISPLAY_VERSION`.
- Only a frozen Windows build (`sys.frozen` and `sys.platform == "win32"`) offers the button. Linux, browser mode and
  the phone show the version and a link to the download page instead.
- The first version carrying the updater is still installed by hand; say so in its release note.

## 9B3 The helper: swap folders with rollback · L
**Flow.** Settings › Restart to update: refuse if the lend rule above applies; lock the open profile through the
normal lock path (drain, close, wipe keys, release lock); start `staged\Lightning.exe --finish-update
--install "<current folder>" --old-pid <pid> --from <old version>`; exit.
**Helper** (runs from the staged folder, so the install folder is free to rename; logic in a platform-neutral
module with the OS calls injected):
1. Wait up to 60 s for the old PID to exit; else give up and relaunch nothing (old app is still open).
2. Delete any older `<install>.previous`; rename `<install>` to `<install>.previous` (retry 10 times over 10 s for
   antivirus or Explorer holding files; on failure relaunch the old app with a message and stop).
3. Copy `staged\` to `<install>.incoming`, check every file against `FILES.sha256`, rename it to `<install>`.
   Any failure: delete `.incoming`, rename `.previous` back, relaunch old.
4. Launch `<install>\Lightning.exe --after-update <old version>`. The new app writes
   `%LOCALAPPDATA%\Lightning\updates\ok-<version>` when its profile chooser has loaded (before any unlock or
   migration). If that file does not appear within 90 s, or the process exits first: rename `<install>` to
   `<install>.failed`, `.previous` back to `<install>`, launch the old app with `--update-failed <version>`.
5. On success the new app deletes the staged folder and ZIP at its next start; `.previous` stays until the next
   update. Log each step (no personal data) to `…\updates\update.log`.
An old version opened from `.previous` already refuses a profile the new one migrated; that message stays.
**Done when:** Linux tests drive the module with a fake filesystem and process layer through: success, old app never
exits, rename blocked, copy corrupt, new app crashes, new app hangs, and power loss between each step (the next
start finds `.previous` or `.incoming` and repairs to one working folder). The lend rule has its own test with real
borrower control stores in each state.

## 9B4 The Settings section and its words · M
In `ui/templates/settings/index.html`, a "Lightning version" block (guideline A: soft wells, Ink headers; no new
style). States and English copy (Arabic for each through the normal i18n, then run the arabic-check skill;
voice: `guideline/brand-voice.md`):
- Idle: "Version 2.0.3" · button "Check for updates".
- Up to date: "You have the newest version."
- Available: "Version 2.0.4 is ready · 31 MB" · "Download" · link "What's new" (website release notes).
- Working: "Downloading… 40%", then "Checking it works on this PC…".
- Ready: "Restart to update" with "Lightning will close and open again. Your profiles stay as they are."
- Refused, lend: "Hand <profile> back to your phone first, then update."
- Refused, folder: "Lightning can't update itself in this folder. Download the new version instead." + link.
- Failed: plain reason + "Download it yourself" link.
- After update (`--after-update`): a one-time notice "Updated to 2.0.4." After `--update-failed`: "The update to
  2.0.4 didn't start, so you're back on 2.0.3." + link to report it.
Progress is read by a small polling endpoint; no figures are computed in JavaScript.
**Done when:** route tests for every state with the 9B2 module faked; Mohab still passes; A16 checked; Arabic check
clean. ARCHITECTURE "Updating" bullet and `packaging/APP_README.txt` describe the button; Glossary gains
"update manifest".

## 9B5 Try it on a real Windows PC · owner
With dummy profiles, from a build carrying the updater to the next release: update; update with a profile borrowed
(refused, then allowed after hand-back); update from a read-only folder (refused); force a failed start (old version
comes back); open the `.previous` copy by hand. Report each as passed or failed in the item.
Before that release is tagged: a separate update key exists (`tools/store_keygen.py <file> --id update-2026-1`),
its public key is in `update_keys.json` beside `store-2026-1`, and `UPDATE_SIGNING_KEY` holds the new JWK.
