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

## 11B2 Bank SMS within Play's SMS policy · M · opus
Owner, 2026-11-09: declare it from day one (`ai/PROJECT_OVERVIEW.md` › Google Play launch).
Files: `SmsBridge.java`, `lightning/ui/templates/phone/sms.html`, `lightning/sms_imports.py`, `docs/google-play.md` (11B5).
Do: filter people's numbers in the content-resolver query, not after reading (`ADDRESS` not matching `^\+?\d{7,}$`, the `PERSON` rule); move the disclosure to the top of From SMS so it is the first thing seen before the system question; write the Permissions Declaration answers ("SMS-based money management", core feature, what is read, where it stays) and the demo video's script into `docs/google-play.md`.
Done when: a test proves `since()` asks the provider with the sender filter and that the disclosure precedes the Allow button; the owner files the declaration with the video (11B7).

## 11B3 Themes sold through Google Play Billing in the Play build · L · opus
Owner, 2026-11-09: sell themes in the Play build with Play Billing (`ai/PROJECT_OVERVIEW.md` › Google Play launch).
Files: `android/app/build.gradle.kts` (Play Billing Library, a `play` flavour), a new `BillingBridge.java`, `lightning/ui/entitlements.py`, `lightning/ui/templates/settings/index.html:22-25`; website: a Supabase edge function that verifies a Play purchase token (Google Play Developer API) and issues the same signed licence `redeem` returns (`skills/supabase-migration`).
Do: one in-app product per paid theme (ids = theme ids); in the Play build Settings shows Play's price and a Buy button, and keeps "Unlock a theme you bought" for codes; no website price or link anywhere in the Play build; purchase → token → edge function verifies and acknowledges → signed licence kept as today. The GitHub APK and the PC are unchanged.
Done when: tests render Settings with the Play flag (Play price, no `marketplace` link) and the edge function's test accepts a valid test token and refuses a reused or refunded one; a licence-test purchase on the internal track unlocks Papyrus (owner, 11B9).

## 11B4 A privacy notice that covers the app, linked from the app · M · opus
Files: website `privacy.html` and `ar/privacy.html` (version 6), app `settings/index.html` (a Privacy row opening the notice in the browser), `lightning/ui/i18n*.py`.
Do: an **App** section: no account, no analytics, data only on your devices; what it sends and to whom (price sites: tickers and fund ids; the store: the unlock code, theme ids and profile id; the journal relay: encrypted mail it cannot read; local network: pairing); SMS read and kept on the phone, only from bank senders; Share to Lightning; how to delete (delete the profile; the unlock record goes with the website account). Remove "does not cover the Lightning app" and "only to look up prices".
Done when: both repos merged; the app's Settings opens `https://lightningeg.com/privacy.html#app` (`/ar/…` in Arabic).

## 11B5 Data safety and Console declarations, drafted · S · opus
Files: new `docs/google-play.md` (for the owner: every Console answer, with the reason from the code).
Do: Data safety (from r29 › Privacy), foreground service `dataSync` (what the lend-and-listen service does; the video's script), financial features (personal budgeting, no loans or payments), content rating, target audience 18+, ads: none, app access: the steps to open the demo household.
Done when: the owner can fill the Console from that page alone.

## 11B7 Owner: the developer account and the listing · owner
Developer account (organisation if a D-U-N-S number is practical; a personal account needs 11B8); a payments profile and the theme products for 11B3; the SMS declaration and video for 11B2; store listing in English and Arabic: icon 512 px, feature graphic 1024 × 500, 4-8 phone screenshots taken after IV-11E and IV-11D, short and full description in the brand voice.

## 11B8 Owner: closed test, 12 testers for 14 days · owner
Only for a personal account made after 2023-11-13: 12 testers opted in for 14 days in a row, then apply for production.

## 11B9 Owner: the phone check before production · owner
Install the internal-test build: Back walks pages, Recents is blank, the SMS question (if kept) follows the disclosure, nothing offers to buy.
