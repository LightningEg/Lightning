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

## 11B5 Data safety and Console declarations, drafted · S · opus
Files: new `docs/google-play.md` (for the owner: every Console answer, with the reason from the code).
Do: Data safety (from r29 › Privacy), foreground service `dataSync` (what the lend-and-listen service does; the video's script), financial features (personal budgeting, no loans or payments), content rating, target audience 18+, ads: none, app access: the steps to open the demo household.
Done when: the owner can fill the Console from that page alone.

## 11B7 Owner: the developer account and the listing · owner
The SMS declaration answers and the video script are in `docs/google-play.md` (11B2 built them). Developer account (organisation if a D-U-N-S number is practical; a personal account needs 11B8); a payments profile and the theme products for 11B3 (one in-app product per paid theme, product id = theme id: `cotton`, `dendera`, `nile`, `papyrus`), a Google Cloud service account with Play Console access to the app (View financial data, Manage orders), its JSON key saved in Supabase as the `redeem-play` secret `GOOGLE_PLAY_SERVICE_ACCOUNT` with `PLAY_PACKAGE_NAME=org.lightning.app`, and a licence tester for the internal track; the SMS declaration and video for 11B2; store listing in English and Arabic: icon 512 px, feature graphic 1024 × 500, 4-8 phone screenshots taken after IV-11E and IV-11D, short and full description in the brand voice.

## 11B8 Owner: closed test, 12 testers for 14 days · owner
Only for a personal account made after 2023-11-13: 12 testers opted in for 14 days in a row, then apply for production.

## 11B9 Owner: the phone check before production · owner
Install the internal-test build: Back walks pages, Recents is blank, the SMS question follows the disclosure, Settings shows no website price or link, and a licence-test purchase of Papyrus unlocks it (and a second device of the same profile unlocks by itself).
