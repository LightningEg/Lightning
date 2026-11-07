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

## 9B6 Before the release that carries the updater · owner
9B1-9B4 are built and merged (ARCHITECTURE › Build and release, Updating). **9B5, the owner's try on a real Windows PC,
is done: the owner reported the result good on 2026-11-07** (no per-case detail was recorded: update, borrowed profile
refused then allowed, read-only folder refused, failed start rolled back, `.previous` opened by hand).
What is left before the tag:
1. The separate update key: the owner made `update-2026-1` and set the `production-release` secret `UPDATE_SIGNING_KEY`
   to its JWK (2026-11-07). **Still to do: add its public key to `lightning/security/update_keys.json` beside
   `store-2026-1`.** The tag run fails (signing refuses a key the app does not pin) until that is merged.
2. ~~Website pages~~ none needed: the app links to the site's existing Downloads hub and release log
   (`entitlements.UPDATE_PATHS`; after the tag the site gets its usual release update, README › Version identity and archive).
3. The release note for the version that carries the updater says it is installed by hand (in 2.1.0's notes); the first
   real self-update is the release after it. The tag run is also the first time CI signs `UPDATE.json` for real.
