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

Each step is one pull request, except the owner's. Read only the files a step names. Android steps need the **Phone app** workflow
run by hand for evidence (AGENTS §2: Android minutes cost money; run once per step, not per push).

## 11B1 A release bundle that Play accepts · M · opus
Files: `android/app/build.gradle.kts`, `android/app/src/main/AndroidManifest.xml`, `MainActivity.java`, `.github/workflows/android-app.yml`, `packaging/phone_build.py`.
Do: a `release` build type (not debuggable) and `bundleRelease`; `targetSdk = 36`, `compileSdk = 36`; replace `onBackPressed()` with an `OnBackInvokedCallback` (API 33+) or `OnBackPressedDispatcher`, same behaviour (page back, then Home, then `moveTaskToBack`), and set `android:enableOnBackInvokedCallback="true"`; `ProbeActivity` only in debug (a `debug` source-set manifest). The signing job signs the AAB with the **upload** key (Play App Signing keeps the app key); the GitHub APK keeps today's key.
Done when: the workflow uploads an `.aab` that `bundletool validate` accepts, `aapt2 dump badging` shows `targetSdkVersion:'36'` and no `debuggable`, and Back on a real phone walks pages then Home then leaves (owner check folded into 11B9).

## 11B2 Bank SMS within Play's SMS policy · M · opus
Files: `SmsBridge.java`, `AndroidManifest.xml`, `lightning/ui/templates/phone/sms.html`, `lightning/sms_imports.py`.
Do: (a) a Play build flavour without `READ_SMS` (paste and Share to Lightning keep working), chosen by the owner's answer recorded in `ai/PROJECT_OVERVIEW.md`; (b) for the build that keeps it: filter people's numbers in the content-resolver query, not after reading (`ADDRESS` not matching `^\+?\d{7,}$`, the `PERSON` rule), and move the disclosure above Paste so it is the first thing on From SMS before the system question.
Done when: a test proves `since()` asks the provider with the sender filter; `aapt2 dump permissions` of the Play AAB lists no SMS permission (option a).

## 11B3 No other way to pay inside the Play build · S · sonnet
Files: `lightning/ui/templates/settings/index.html:22-25`, `lightning/ui/entitlements.py`, the Android build flavour from 11B2 (a build flag Python can read, as `build_identity.txt` is).
Do: in the Play build, Settings keeps "Unlock a theme you bought" (enter a code) but drops "Buy it on lightningeg.com" and the See prices link, and no other page names a price or links to the marketplace. The GitHub APK and the PC are unchanged.
Done when: a test renders Settings with the Play flag and finds no `marketplace` link and no price.

## 11B4 A privacy notice that covers the app, linked from the app · M · opus
Files: website `privacy.html` and `ar/privacy.html` (version 6), app `settings/index.html` (a Privacy row opening the notice in the browser), `lightning/ui/i18n*.py`.
Do: an **App** section: no account, no analytics, data only on your devices; what it sends and to whom (price sites: tickers and fund ids; the store: the unlock code, theme ids and profile id; the journal relay: encrypted mail it cannot read; local network: pairing); SMS read and kept on the phone, only from bank senders; Share to Lightning; how to delete (delete the profile; the unlock record goes with the website account). Remove "does not cover the Lightning app" and "only to look up prices".
Done when: both repos merged; the app's Settings opens `https://lightningeg.com/privacy.html#app` (`/ar/…` in Arabic).

## 11B5 Data safety and Console declarations, drafted · S · opus
Files: new `docs/google-play.md` (for the owner: every Console answer, with the reason from the code).
Do: Data safety (from r29 › Privacy), foreground service `dataSync` (what the lend-and-listen service does; the video's script), financial features (personal budgeting, no loans or payments), content rating, target audience 18+, ads: none, app access: the steps to open the demo household.
Done when: the owner can fill the Console from that page alone.

## 11B6 Privacy on screen: Recents and notifications in context · S · sonnet
Files: `MainActivity.java`, `lightning/ui/templates/phone/settings…` (the This phone section).
Do: `setRecentsScreenshotEnabled(false)` (API 33+) and `FLAG_SECURE` while amounts are hidden or by a "Hide in recent apps" switch (on by default); ask for notifications when the person first turns a reminder on, not at first start.
Done when: a test renders the switch; on a phone the Recents card is blank (owner check in 11B9).

## 11B7 Owner: the developer account and the listing · owner
Developer account (organisation if a D-U-N-S number is practical; a personal account needs 11B8); store listing in English and Arabic: icon 512 px, feature graphic 1024 × 500, 4-8 phone screenshots taken after IV-11E and IV-11D, short and full description in the brand voice.

## 11B8 Owner: closed test, 12 testers for 14 days · owner
Only for a personal account made after 2023-11-13: 12 testers opted in for 14 days in a row, then apply for production.

## 11B9 Owner: the phone check before production · owner
Install the internal-test build: Back walks pages, Recents is blank, the SMS question (if kept) follows the disclosure, nothing offers to buy.
