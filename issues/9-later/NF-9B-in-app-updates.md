---
title: In-app updates on Windows
type: feature
pillar: everywhere
size: M
model: opus
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

## What is left (2026-11-08)

9B1-9B4 are built and merged (#365, #367, #372; ARCHITECTURE › Build and release, Updating). **9B5, the owner's try on
a real Windows PC, is done: the owner reported it good on 2026-11-07** (no per-case detail was recorded). The release
note that says 2.1.0 is installed by hand is already in `ai/changelog/2.1.0.md` (2026-11-08 check). The owner made the
separate update key `update-2026-1` and set the `production-release` secret `UPDATE_SIGNING_KEY` to its private JWK
(2026-11-07). Checked 2026-11-08: `lightning/security/update_keys.json` still pins only `store-2026-1`, so the tag
run would fail (`packaging/update_manifest.py` `sign` refuses a key the app does not pin). Source version is 2.1.0
(`lightning/__init__.py`, `pyproject.toml`).

## How to work on this item

One step is one pull request; the owner steps need no code. Read only the files a step names. The tests are
`python -m pytest tests/test_update_manifest.py tests/test_desktop_update.py -q`. Delete the step's heading in the
same commit; when 9B9 is done, delete this file and add 9B to the folder's `done:`.

## 9B6 Owner: give the update key's public half · owner
Post in the session (or a GitHub issue) the line `tools/store_keygen.py --id update-2026-1` printed when the key was
made: `Public, safe to share:  "update-2026-1": "<43 characters>"`. Only the public half; never the JWK. If that line
was not kept, the public key is the JWK's `x` field: copy only `x`. If the key is lost, make a new one with
`python tools/store_keygen.py --id update-2026-2`, set the secret again, and post that public line instead.

## 9B7 Pin the update key in the app · S · opus
Starts when 9B6 has given the public line. Opus because it is a trust key: check the value, do not trust a pasted
one blindly.
Files: `lightning/security/update_keys.json`, `tests/test_update_manifest.py:39`
(`test_the_pinned_update_keys_start_with_the_store_key`), `tests/test_desktop_update.py:143`.
Do: add `"update-2026-1": "<public>"` beside `store-2026-1` (keep the store key so nothing signed with it is refused);
update the file's `comment` to say CI signs with `update-2026-1`. Check the value is 43 base64url characters that
decode to 32 bytes (`python -c "import base64;print(len(base64.urlsafe_b64decode('<public>='))"` prints 32) and is
not the store key. Rename and change the test to
`test_the_pinned_update_keys_are_the_store_key_and_update_2026_1`: the keys are exactly those two, the store key equals
`store_keys.json`'s, and the update key differs from it. Do not edit `ai/changelog/` by hand; the commit's
`Release-note: none`.
Done when: `python -m pytest tests/test_update_manifest.py tests/test_desktop_update.py -q` passes, and
`python -m lightning.desktop.update` is not needed: `packaging/update_manifest.py`'s `load_keys()` returns both ids
(`python -c "import sys;sys.path.insert(0,'packaging');import update_manifest as u;print(sorted(u.load_keys()))"`).

## 9B8 Owner: approve the v2.1.0 tag · owner
Needs 9B7 merged first. An AI runs skill `release-check` steps 1-7 and reports; the owner then approves the tag
(it publishes to the public downloads repository and cannot be undone). After the tag run, check its log says
`Signed UPDATE.json for 2.1.0 with update-2026-1` and that the release has `UPDATE.json` and `UPDATE.json.sig`.
If signing fails, nothing is published; the fix is 9B7, not a new key.

## 9B9 The site's release update for 2.1.0 · M · opus
Needs 9B8 done (the release exists). Two repositories, so opus.
Files: the website repository's README › Version identity and archive (the site's release steps), skill
`website-sync` (`skills/website-sync/SKILL.md`), `lightning/ui/entitlements.py` (`UPDATE_PATHS`: the pages the app's
update block opens; they must keep working).
Do: the site's usual release update for 2.1.0 (download links, version IDs, release log in English and Arabic), as
`website-sync` says. Do not mention that 2.1.0 updates itself; say later versions will.
Done when: `website-sync`'s checks pass in both repositories, and each path in `UPDATE_PATHS` answers 200 on the
live site (`curl -sI https://<site>/<path>`).
