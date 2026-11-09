---
title: One purchase per person - a theme bought on Google Play or the website unlocks every profile of that buyer, on every surface
type: feature
pillar: own
size: L
model: opus
status: ready
created: 2026-11-09
by: Claude
---

## Report

Google Play sells a theme once per Google account (a non-consumable product), while Lightning bound each purchase to one
profile: the Play build tied the token to the first profile (`redeem-play` answers 409 for any other) and the website
sells extra profiles as seats at 25% of the price. A person with two profiles on one phone could not unlock the second:
Play says "You already own this" and the store refuses. Owner, 2026-11-09: **one purchase per person**, the same rule on
every surface.

## Owner decisions (2026-11-09)

| Question | Decision |
|---|---|
| Play | One purchase unlocks the theme on every profile opened in the Play build with that Google account. |
| Website | The same: account-wide. Extra-profile seats at 25% go; a code for another profile is free; a cap of 10 profiles per purchase only stops code sharing. |
| Website purchase, Play phone | Through the profile: unlock on the PC (or the GitHub APK); the licence syncs with the profile. The Play build has no code box and no website mention (Play payments policy). |
| Refund on Play | The store refuses new profiles for a refunded or voided purchase; licences already issued stay (they work offline). |
| Price | One price in EGP on Play and the website, on a Play price step; the 15% Play fee is absorbed. Numbers are the owner's (10H5). |

## Every case

The signed licence still names one profile (it is what makes a theme work offline and travel with the profile); what
changes is how many licences one purchase may mint. "Profile" is the profile's stable id, the same on all its devices.

| # | Situation | What happens |
|---|---|---|
| 1 | Buys on Play, profile A | Play sheet → `redeem-play` → licence for A. A's PC and other phones wear it after the next sync. |
| 2 | Same phone, opens profile B (same Google account) | Settings settles Play's purchases: Play reports the theme owned, `redeem-play` mints a licence for B. No second payment, no Buy button. |
| 3 | Reinstall, or a new phone with the same Google account | The restored profile already carries its licence; a new profile gets one from Play's owned list as in 2. |
| 4 | Profile A opened on a phone signed into another Google account | A's licence travels with A, so A wears it. That phone's other profiles do not. |
| 5 | Buys on the website, profile on the PC | Website code → licence for that profile (unchanged), now free for each further profile of that website account, up to 10. |
| 6 | Website buyer, the same profile on a Play phone | The profile's licence syncs (pairing or backup restore); the Play build wears it and shows no Buy for it. |
| 7 | Website buyer, a phone-only profile in the Play build | Not reachable in the Play build (no code box). They unlock it once in the GitHub APK or on a PC, or buy on Play. Said on the website's marketplace, never in the Play build. |
| 8 | Bought on Play, wants it on a PC-only profile | Open that profile once in the Play build (or pair it to the phone) to mint its licence; the PC has no Play. The website shows nothing for Play purchases (Play owns that record). |
| 9 | Would pay twice | The Play build offers Buy only for themes the open profile does not wear; the website marks a theme Owned for its account. A person can still buy on both by choice; nothing merges the two records. |
| 10 | Pending payment (Play cash or slow method) | Unchanged: "It unlocks when Google Play confirms it"; settled on the next Settings load. |
| 11 | Refund or chargeback on Play | `redeem-play` checks the order (and Google's voided purchases); refused purchases mint no new licences (410). Existing licences stay. |
| 12 | Eleventh profile on one purchase | Refused with a message naming the cap; the owner can free a profile in the console (existing Members › Free a profile). |
| 13 | Already sold extra seats (25%) | Owner decides in 10H5 (credit the coins back is the fair default). |

## Fix

Steps, in order; each is one pull request.

## 10H1 Store: a Play purchase mints many profiles · M
Website repo. `redeem-play` keeps every profile a purchase token unlocked (`play_purchases` gains a profile list or a
child table; cap 10), mints a licence for each new one instead of 409, refuses a refunded, cancelled or voided order
with 410 (Google's purchase state and the Voided Purchases API), and acknowledges as today. Postgres tests for 2, 11, 12.

## 10H2 App: settle for every profile, say so · S
`lightning/ui/play_store.py` already redeems each owned purchase for the open profile; reword the 409 and cap messages,
and Settings' Play copy ("Bought once, every profile on this Google account wears it", English and Arabic).
`BillingBridge` keeps the obfuscated profile id only as the first buyer's. Docstrings in `entitlements.py`,
Architecture › Two stores, `docs/google-play.md` › In-app products. Tests in `tests/test_play_billing.py` for 2 and 3.

## 10H3 Website: account-wide seats · M
Website repo. A member's purchase claims up to 10 profiles at no charge (codes free per profile); remove the 25% extra
profile price from the marketplace, checkout and owner console, English and Arabic; marketplace says how a website
theme reaches a Play phone (case 7). Migration plus `seats.test.mjs`.

## 10H4 Owner: prices · owner
One EGP price per theme on a Play price step, the same coins on the website; set the four Play products (`cotton`,
`dendera`, `nile`, `papyrus`) to it; confirm the Play service fee tier in the Console.

## 10H5 Owner: the extra seats already sold · owner
Credit their coins back (recommended) or leave them.

Read: `lightning/ui/play_store.py`, `lightning/ui/entitlements.py` (`redeem_play`, `_exchange`), the website's
`supabase/functions/redeem-play` and `redeem-purchase`, [NF-11B](../11-phone-ux/NF-11B-ship-the-phone-on-google-play.md).
