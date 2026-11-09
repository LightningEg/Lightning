---
title: Ship the phone on Google Play - a release bundle at API 36, the SMS and payments policies, the app's own privacy notice and the Console declarations
type: feature
pillar: everywhere
size: L
model: opus
status: ready
post: no
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

Report [r29](r29-google-play-readiness/report.md) blockers B1-B6 and findings S6-S10, T14, T15. Today the phone is a debug APK
targeting API 35, asks for `READ_SMS`, links to the website to buy themes, and no privacy notice covers it. Play takes none of that.

## How to work on this item

The code steps are done (11B1-11B6). What is left is the owner's; every Console answer, with its reason from the code, is in
[docs/google-play.md](../../docs/google-play.md).

## 11B7 Owner: the developer account and the listing · owner
The SMS declaration answers and the video script are in `docs/google-play.md` (11B2 built them). Developer account (organisation if a D-U-N-S number is practical; a personal account needs 11B8); a payments profile and the theme products for 11B3 (one in-app product per paid theme, product id = theme id: `cotton`, `dendera`, `nile`, `papyrus`), a Google Cloud service account with Play Console access to the app (View financial data, Manage orders), its JSON key saved in Supabase as the `redeem-play` secret `GOOGLE_PLAY_SERVICE_ACCOUNT` with `PLAY_PACKAGE_NAME=org.lightning.app`, and a licence tester for the internal track; the SMS declaration and video for 11B2; store listing in English and Arabic: icon 512 px, feature graphic 1024 × 500, 4-8 phone screenshots taken after IV-11E and IV-11D, short and full description in the brand voice.

**Signing key (owner, 2026-11-09):** Play App Signing uses the existing app key (the `ANDROID_KEYSTORE_*` one that signs the GitHub APK), uploaded with Play's PEPK tool, so a GitHub install updates from Play without losing data. A separate upload key signs the bundle (`ANDROID_UPLOAD_*` in the `android-signing` environment).

**Before the first submission (owner, 2026-11-09):** IV-11A, IV-11E and IV-11D; screenshots after those. The upload key works (Phone app run 42634615473 signed the bundle).

## 11B8 Owner: closed test, 12 testers for 14 days · owner
Only for a personal account made after 2023-11-13: 12 testers opted in for 14 days in a row, then apply for production.

## 11B9 Owner: the phone check before production · owner
Install the internal-test build: Back walks pages, Recents is blank, the SMS question follows the disclosure, Settings shows no website price or link, and a licence-test purchase of Papyrus unlocks it (and a second device of the same profile unlocks by itself).
