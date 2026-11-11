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
| Website | The same: account-wide. Extra-profile seats at 25% go; a code for another profile is free; a cap of 5 profiles per purchase (owner, 2026-11-11; was 10) only stops code sharing. |
| Website purchase, Play phone | Through the profile (unlock on the PC or the GitHub APK; the licence syncs), or the Play build's neutral **Unlock code** field. The Play build never names the website (Play payments policy). |
| Refund on Play | The store refuses new profiles for a refunded or voided purchase; licences already issued stay (they work offline). |
| Price | One price in EGP on Play and the website; the 15% Play fee is absorbed. Owner, 2026-11-11: Nile 60, Cotton 120, Papyrus 200, Dendera 200 EGP (300/600/1,000/1,000 coins), unchanged. |
| Play to the website | Owner, 2026-11-11: through the profile id (10H6). A buyer must always be able to get a code again: website buyers press Get app code any time; Play buyers once their profile is linked. |

## Every case

The signed licence still names one profile (it is what makes a theme work offline and travel with the profile); what
changes is how many licences one purchase may mint. "Profile" is the profile's stable id, the same on all its devices.

| # | Situation | What happens |
|---|---|---|
| 1 | Buys on Play, profile A | Play sheet → `redeem-play` → licence for A. A's PC and other phones wear it after the next sync. |
| 2 | Same phone, opens profile B (same Google account) | Settings settles Play's purchases: Play reports the theme owned, `redeem-play` mints a licence for B. No second payment, no Buy button. |
| 3 | Reinstall, or a new phone with the same Google account | The restored profile already carries its licence; a new profile gets one from Play's owned list as in 2. |
| 4 | Profile A opened on a phone signed into another Google account | A's licence travels with A, so A wears it. That phone's other profiles do not. |
| 5 | Buys on the website, profile on the PC | Website code → licence for that profile (unchanged), now free for each further profile of that website account, up to 5. |
| 6 | Website buyer, the same profile on a Play phone | The profile's licence syncs (pairing or backup restore); the Play build wears it and shows no Buy for it. |
| 7 | Website buyer, a phone-only profile in the Play build | Not reachable in the Play build (the Play build's Unlock code field, which never names the website). They unlock it once in the GitHub APK or on a PC, or buy on Play. Said on the website's marketplace, never in the Play build. |
| 8 | Bought on Play, wants it on a PC-only profile | Open that profile once in the Play build (or pair it to the phone) to mint its licence; the PC has no Play. The website shows nothing for Play purchases (Play owns that record). |
| 9 | Would pay twice | The Play build offers Buy only for themes the open profile does not wear; the website marks a theme Owned for its account. A person can still buy on both by choice; nothing merges the two records. |
| 10 | Pending payment (Play cash or slow method) | Unchanged: "It unlocks when Google Play confirms it"; settled on the next Settings load. |
| 11 | Refund or chargeback on Play | `redeem-play` checks the order (and Google's voided purchases); refused purchases mint no new licences (410). Existing licences stay. |
| 12 | Sixth profile on one purchase | Refused with a message naming the cap; the owner can free a profile in the console (existing Members › Free a profile). |
| 13 | Already sold extra seats (25%) | Owner decides in 10H5 (credit the coins back is the fair default). |

## Fix

Steps, in order; each is one pull request. Built: 10H1, 10H2 (app and `redeem-play`), 10H3 (website #186: a website purchase covers up to 10, now 5 profiles free, no 25% seats).

## 10H4 Owner: set the prices in the Console · owner
Prices decided (above). Create the four Play products (`nile` 60, `cotton` 120, `papyrus` 200, `dendera` 200 EGP), set
Egypt's price by hand, confirm the 15% service fee tier. Steps: [docs/google-play.md](../../docs/google-play.md) › In-app products.

## 10H5 Owner: the extra seats already sold · owner
Credit their coins back (recommended) or leave them.

## 10H6 A Play purchase reaches the buyer's website account, through the profile id · L · opus
Today a Play purchase lives only in `private.play_purchase_profiles` (token hash, profile id); the website account
knows nothing, so the theme does not dress the site and the website cannot give a code again. Owner, 2026-11-11: link
by the profile id, never by Google sign-in (Play never tells us the buyer's Google account).

1. Website: **Link the app** on the account page issues a link code (the activation-ticket pattern in reverse: ten
   minutes, single use, hashed).
2. App, PC and GitHub APK only (the Play build never names the website): Settings › Appearance › *Add this profile to
   your website account* takes the code and sends it with the profile id to a new `link-profile` function.
3. The store records the profile under that account (`profile_claims`), finds every Play token that unlocked the same
   profile, and adds each theme to the account's inventory as owned through Play (`source = 'play'`): the site wears it,
   the marketplace says Owned, and Get app code works for it, all inside the same cap of 5.
4. A Play refund or void found later by `redeem-play` removes that inventory row; licences already issued stay.
5. Tests: the link on Postgres (the code, the cap shared with website purchases, a refunded token not linked, a profile
   another account claims refused), the app form, Arabic; the website copy in both languages.

Done when a Play buyer links once on the PC and the website shows the theme Owned, wears it, and issues a code for a
new PC-only profile.
Read: `lightning/ui/play_store.py`, `lightning/ui/entitlements.py` (`redeem_play`, `_exchange`), the website's
`supabase/functions/redeem-play` and `redeem-purchase`, NF-11B (done).
