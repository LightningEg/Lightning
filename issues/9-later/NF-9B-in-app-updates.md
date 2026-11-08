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

## What is left (2026-11-09)

9B1-9B4 are built and merged (#365, #367, #372; ARCHITECTURE › Build and release, Updating). The owner reported
9B5's real Windows check good on 2026-11-07 (no per-case detail was recorded).
9B6-9B7: the owner supplied the public half of `update-2026-2` and confirmed its private JWK is saved as the
`production-release` environment secret `UPDATE_SIGNING_KEY`. The app now pins that public key beside
`store-2026-1`; `tests/test_update_manifest.py::test_the_pinned_update_keys_are_the_store_key_and_update_2026_2`
and `tests/test_desktop_update.py` verify the key set and agreement between publisher and app.

The existing `v2.1.0` tag points to `930530a3`, before the update key was pinned. Its run is
https://github.com/LightningEg/Lightning/actions/runs/42527383359. Do not move the tag or rerun it expecting the
new key to work. The owner chose to prepare **v2.1.1** with this fix (2026-11-09); preserve the old tag.

## How to work on this item

One step is one pull request; the owner steps need no code. Read only the files a step names. The tests are
`python -m pytest tests/test_update_manifest.py tests/test_desktop_update.py -q`. Delete the step's heading in the
same commit; when 9B9 is done, delete this file and add 9B to the folder's `done:`.

## 9B8 Prepare and approve the v2.1.1 tag · owner
Needs the key fix merged first. An AI runs skill `release-check` steps 1-7 and reports; the owner then approves the tag
(it publishes to the public downloads repository and cannot be undone). After the tag run, check its log says
`Signed UPDATE.json for 2.1.1 with update-2026-2` and that the release has `UPDATE.json` and `UPDATE.json.sig`.
If signing fails, nothing is published; compare the pinned public key with the configured signing key.

## 9B9 The site's release update for 2.1.1 · M · opus
Needs 9B8 finished first (the release exists). Two repositories, so opus.
Files: the website repository's README › Version identity and archive (the site's release steps), skill
`website-sync` (`skills/website-sync/SKILL.md`), `lightning/ui/entitlements.py` (`UPDATE_PATHS`: the pages the app's
update block opens; they must keep working).
Do: the site's usual release update for 2.1.1 (download links, version IDs, release log in English and Arabic), as
`website-sync` says. Explain that the first updater build is installed by hand; later versions can use its updater.
Done when: `website-sync`'s checks pass in both repositories, and each path in `UPDATE_PATHS` answers 200 on the
live site (`curl -sI https://<MARKETPLACE_HOST><path>`, host from `entitlements.py`).
