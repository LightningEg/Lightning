# Audit 15: is the phone ready for Google Play? Security, privacy, tab by tab, themes and motion

Date: 2026-11-09 · Author/reviewer: Claude (Opus), on the owner's request
Repository: both (app; the website's privacy notice) · Reviewed commit: ea1c96c3e40f254636cfa44797af972d14dcf9b8 (app; the fixes are on 3e58e11) · website 726734215fbc513c3e50472c4a214c2ed9f8691c
Code: r29

## Scope and method

The owner asked: am I ready for a Google Play demo, in security and privacy; and a full, tab-by-tab audit of the phone, its
themes and its motion, with the two Arabic commas and "not a single visual, a block of text" named.

- **Build and policy:** `android/` (manifest, Gradle, Java bridges, network and backup rules), `.github/workflows/android-app.yml`,
  `lightning/ui/entitlements.py`, the SMS path (`SmsBridge.java`, `lightning/sms_imports.py`, `phone/sms.html`), every outbound
  URL in `lightning/`, and the website's `privacy.html` (version 5, 2026-11-04). Google Play rules checked on 2026-11-09 (sources at
  the end); where a rule could only be read in secondary sources it says so.
- **Screens:** the phone app (`profile_app(..., phone=True)`) on a throwaway encrypted profile with the demo household, at 412 × 892
  (the owner's phone), English and Arabic, all seven themes; Chromium (Playwright). Scripts: [evidence/scripts](evidence/scripts/).
- **Motion:** `document.getAnimations()` on each theme, and screen recordings of the page change, the Safe to spend sheet, the row
  swipe and the Add sheet (recordings are made by `video.py`; stills are in [evidence/shots](evidence/shots/)).
- Not checked: a real Android device, Play Console itself, the merged release manifest of a release build, the native libraries'
  16 KB alignment in an APK (android/README says it is built in).

## Verdict

**Not ready for a production listing today. Ready for an internal test track after six blockers (B1-B6).** Security is strong for
a local-first finance app; the gaps are packaging, two Play policies (SMS and payments) and a privacy notice that excludes the app.
The phone itself works end to end but reads as text: no chart on any tab, To do rows as sentences, and paid themes that barely
change the phone.

| # | Blocker | Why Play stops it | Item |
|---|---|---|---|
| B1 | The build is a debug APK (`assembleDebug`) targeting API 35 | Play takes only a release **AAB** (Play App Signing, upload key), not debuggable; new apps and updates must target **API 36** since 2026-08-31 | NF-11B1 |
| B2 | `onBackPressed()` is the only Back | Targeting API 36 turns predictive back on: `onBackPressed` is no longer called, so Back would leave the app from any page | NF-11B1 |
| B3 | `READ_SMS` in the manifest | A restricted permission: needs the Permissions Declaration Form, a demo video, and Google's case-by-case approval ("SMS-based money management" is the exception to claim). Rejection is common; the app already works without it (paste and Share to Lightning) | NF-11B2 |
| B4 | Settings says "Buy it on lightningeg.com. See prices" with a link (`settings/index.html:24`) | Payments policy: digital goods used in the app (themes) must use Play Billing, and the app may not lead users to another way to pay (outside the US and EEA programmes). Egypt is in neither | NF-11B3 |
| B5 | No privacy notice covers the app | Play requires a policy URL for the app and inside the app. `privacy.html` §1 says it "does not cover the Lightning app" and that the app "connects to the internet only to look up prices"; the app also redeems theme codes (POST to the store with a profile id), relays the encrypted journal through Cloudflare, finds devices on the local network and reads SMS on the device | NF-11B4 |
| B6 | Play Console declarations not made | Data safety, foreground service type `dataSync` (with video), financial features, content rating, target audience, app access (the app is password-locked: reviewers need the demo route), and, for a personal account made after 2023-11-13, a closed test with 12 testers for 14 days before production | NF-11B5, OW-11B9 |

## Findings

### Security (what is already right, and what to add)

| ID | Severity | Observation | Evidence | Follow-up |
|---|---|---|---|---|
| S1 | ok | Data never leaves through Google backup or device transfer: `allowBackup=false`, `fullBackupContent=false`, every domain excluded | `res/xml/data_extraction_rules.xml` | none |
| S2 | ok | Cleartext only to `127.0.0.1`; TLS everywhere else | `res/xml/network_security_config.xml` | none |
| S3 | ok | WebView locked to its own origin: other requests get 403, file and content access off, no popups, no geolocation, debugging off, outside links only `https` without user info, handed to the browser | `MainActivity.java:82-237` | none |
| S4 | ok | The loopback server needs a 32-byte cookie token and a one-time launch code on a random port, so another app on the phone cannot read it | `lightning/runtime/http.py:89-216` | none |
| S5 | ok | Profiles are SQLCipher; fingerprint unlock uses Keystore keys that a new fingerprint invalidates; the password always works | `BiometricBridge.java`, `StayBridge.java` | none |
| S6 | medium | Balances show in the Recents thumbnail and in screenshots; the eye hides amounts only when pressed | no `FLAG_SECURE` / `setRecentsScreenshotEnabled` | NF-11B6 |
| S7 | medium | `SmsBridge.since()` reads every inbox message (sender and body) into Python, which then drops people's numbers (`PERSON`, `sms_imports.py:40`). The disclosure promises "never from people's numbers"; the filter belongs in the query | `SmsBridge.java:40-59` | NF-11B2 |
| S8 | low | `ProbeActivity` (the 04a-04c dependency checks) ships in every APK | manifest | NF-11B1 |
| S9 | low | Notifications are asked for on the very first start, before anything says why | `MainActivity.java:146-149` | NF-11B6 |
| S10 | low | Share-to-Lightning keeps up to 50 shared texts in memory unencrypted until read; fine, but say so in the notice | `SmsBridge.java:62-67` | NF-11B4 |

### Privacy and Data safety

What the app sends, from the code (`grep -rhoE 'https://…' lightning`): price lookups to Yahoo Finance, TradingView, Mubasher, the
CBE and GitHub (tickers and fund ids, from the phone's IP); theme unlock to the store's `redeem_url` (the one-time code, the theme
ids and the profile id); the journal's encrypted mailbox to Cloudflare (`sync/journal/cloud.py`: "No data key is sent to the
service"); local-network discovery for pairing; nothing for analytics or crashes. The SMS text is read and kept on the phone.

Draft Data safety answers for the owner to confirm in 11B5: price lookups send only tickers and fund ids to the price sites (decide in 11B5 whether to declare them as "Financial info: other", shared, optional; declaring is the safer answer); the profile id sent with an unlock is a pseudonymous identifier tied to a purchase (collected, required for that feature,
not shared); journal mail is end-to-end encrypted (Google's form does not count data the developer cannot read); SMS processed on
device only (not collected); data encrypted in transit: yes; users can delete: yes (delete the profile; nothing is held by Lightning
except the unlock record, deleted with the website account). The privacy notice needs an **App** section saying the same, linked
from Settings and the store listing, in English and Arabic (website repo, with a version bump of the notice).

### Tab by tab (412 px, demo household)

| ID | Tab | Severity | Observation and what it should be | Evidence | Follow-up |
|---|---|---|---|---|---|
| T1 | All | high | **Not one chart on five tabs.** Budget has bars; nothing else is drawn. The guideline already specifies phone charts (C07: area trend, waterfall, donut, month grid, bars) and Home's meter (C06.1); they were never built on the phone | `shots/en-*.jpg` | IV-11D |
| T2 | Home | medium | **To do is a block of sentences:** "NBE 3-year certificate: 2 interest payments to match", "Emergency fund needs you", "Looks recurring", each with the same "Review". C11.1 wants `Vodafone 350 · in 3 days  Pay ›`: who, how much, when, one verb that says what happens | `shots/en-home.jpg`, owner's screenshot | IV-11E |
| T3 | Home | medium | The hero's line is a warning ("May be off: 3 days not recorded.") or a date ("On top of your plan until 2026-12-01.") instead of C11.1's "About 1,650 a day until payday on …"; the warning should be a To do row | `shots/en-home.jpg` | IV-11E |
| T4 | Home, Activity | low | Every expense has the same pink ↓ disc; nothing tells Carrefour from Vodafone at a glance (category mark or institution logo, C08.2 keeps the arrow meaning) | `shots/en-home.jpg` | IV-11D |
| T5 | Budget | medium | **Needs attention lists categories that are finished** (Health 900 of 900, Housing 12,000 of 12,000, Loans 2,500 of 2,500, each with 0 left) and then lists every one of them again under Your categories. Paid-in-full is not attention; over plan or ahead of pace is | `shots/en-budget.jpg` | BV-11F |
| T6 | Budget | medium | In Arabic a "0 left" is the Arabic zero "٠", which is a dot: four rows end in a lone "•" | `shots/ar-budget.jpg` | BV-11F |
| T7 | Budget | low | Every bar is the same blue whatever its state; a bar at or over plan needs its meaning colour (A03) | `shots/en-budget.jpg` | BV-11F |
| T8 | Add | medium | The tab opens a good sheet (Out/In/Move, amount, account, chips, Save on screen). The full page behind it (`/accounts/add-transaction`, opened from links) has "‹ CIB Payroll" as its title, **Money** lit in the tab bar, an Import / Accounts / Held for others switch above the form, and a 📋 emoji on Paste SMS | `shots/en-add.jpg` | IV-11I |
| T9 | Activity | medium | The same transfer is "To Vodafone Cash −1,000" on Home and "CIB Payroll → Vodafone Cash 1,000" on Activity (A16: one figure, one form). A day's net shows on one date only (2026-11-05 "−2,500") | `shots/en-activity.jpg`, `shots/en-home.jpg` | BV-11G |
| T10 | Activity | low | "In +46,833 · Out −19,001" is a sentence; it is the place for two bars on one scale (C07.3.3) | `shots/en-activity.jpg` | IV-11D |
| T11 | Money | medium | **Cash planning, Spending and Weekly review were listed twice** (the old More list left under the new rows). Fixed in this branch | `shots/en-money-full.jpg` | fixed (r29) |
| T12 | Money | medium | Under Net worth come 21 plain rows (Report … Data checks); no trend (C11.3 + C07.3.1), no split of what you own. The tab wears the "···" More icon though More is retired (C01: a lone icon only when everyone knows it) | `shots/en-money-full.jpg` | IV-11H |
| T13 | Money | low | "Accounts" is underlined like a link while every other heading is plain | `shots/en-money.jpg` | IV-11H |
| T14 | Settings | high (Play) | "Buy it on lightningeg.com. See prices" link (B4); "another computer" is a desktop word on the phone (C12); Settings is a long scroll of PC settings (Sale factors, Target allocation, Price files) with no privacy notice, licences or "delete this profile" | `shots/x-settings.jpg` | NF-11B3, NF-11B4, IV-11H |
| T15 | SMS | medium (Play) | The disclosure exists and is well worded, but sits at the bottom of From SMS under Paste; Play wants it shown before the system question, in the normal flow | `phone/sms.html:57-62` | NF-11B2 |

### Arabic

| ID | Severity | Observation | Evidence | Follow-up |
|---|---|---|---|---|
| A1 | medium | **Two thousands separators:** the same character ٬ (U+066C) drawn by two faces. The lead figure uses Readex Pro (a comma, "٧٤,٠٧٧"); rows use Noto Sans Arabic (a raised tick, "١٢‘٠٠٠"). Fixed here: Readex draws every Arabic-Indic digit and separator in body text too ("Lightning Arabic Figures" in `fonts.css`, `--body` in `style.css`) | `shots/arabic-commas.jpg`, `shots/after-ar.jpg` | fixed (r29) |
| A2 | medium | **Transfers read backwards:** "CIB Payroll ← Vodafone Cash" — the server flips → for Arabic, but two Latin names keep the line left to right, so the arrow pointed into CIB. Fixed here: each name is isolated (`<bdi>`), so the pair lays out right to left | `shots/ar-activity.jpg`, `shots/after-ar.jpg` | fixed (r29) |
| A3 | medium | Account names are translated as if they were UI words: "Cash wallet" is "محفظة نقدية" on Home ("To Cash wallet" matched the dictionary) and "Cash wallet" on Activity. A name the person typed must never be translated | `shots/ar-home.jpg`, `shots/ar-activity.jpg` | BV-11G |
| A4 | low | Chevrons point backwards ("ادفع ›") and dates are yyyy-mm-dd in lists | owner's screenshot | IV-3BG1, IV-3BK (already planned) |
| A5 | low | "داخل +٤٦٬٨٣٣ ، خارج" has a space before the Arabic comma | `shots/ar-activity.jpg` | BV-11G |

### Visuals: what "not a single visual" means in numbers

Figures on screen at 412 × 892 above the tab bar: Home 7 figures, 0 charts, 0 icons that differ; Budget 1 lead + 4 bars;
Activity 9 figures, 0 charts; Money 7 figures, 0 charts. The guideline already allows, per tab, without a new rule: Home, a
meter under Safe to spend (days to payday against money left, C06.1 "a meter when it helps") and the This month row as a
segmented bar; Budget, state colours and one donut or stacked bar of where the month went (C07.2); Activity, the In/Out pair as two
bars (C07.3.3); Money, the 160-tall net-worth trend (C07.3.1) and what you own as a segmented bar. Category marks in rows need an
owner decision (C08.2 keeps the arrow as the row's mark), asked with this report.

### Themes (phone)

| ID | Severity | Observation | Evidence | Follow-up |
|---|---|---|---|---|
| H1 | high (value) | **Paid themes barely reach the phone.** The phone's lead figure sits on the ground with no card (C06.2), and `theme-materials.css:243` gives it "no artwork of its own", so every hero part (lacquer, foil edge, glint, winged disc, lotus line) is PC-only. Phone cards are flat rows, so the card parts have nothing to dress. What changes: background, header, Add disc and the active tab | `shots/themes-home.jpg`, `shots/themes-money.jpg` | IV-10G |
| H2 | high (value) | **Papyrus, sold as "animated" (1,000 coins), runs no animation on the phone:** `getAnimations()` is empty; its motion is the PC hero's edge glint. Dendera and Dendera night run their one 14 s pigment thread in the header, as `themes.md` §6 allows | `getAnimations()` per theme, below | IV-10G |
| H3 | medium | Cotton paints the Add disc rose-red; rose means money going badly (A03), and Add is the most-pressed control | `shots/themes-home.jpg` (third) | IV-10G |
| H4 | low | Contrast and layout hold in all seven: nothing moves between themes, text stays readable on the textured grounds | `shots/themes-*.jpg` | none |

`getAnimations()` on Home after load: default, Cotton, Nile, Papyrus, Royal Obsidian & Gold: none. Dendera, Dendera night:
`m-pigment` on `.phone-appbar::before`, infinite, 14 s.

### Motion (default theme)

What runs, and was recorded working: pages fade into each other (cross-document view transition, 140 ms, `phone.css:960-965`); the
tab and app bars stay still across the change; sheets rise (Safe to spend, the Add sheet); a row swipe reveals Set category and
Delete (`phone-gestures.js`, 180 ms); Save shows a spinner; the chevron of a fold turns; everything stops under reduced motion
(`phone.css:970-1009`). Nothing moves on a figure: no count-up, no bar that fills, no meter that grows; the blue-green seam under
each hero is still. With the charts of IV-11D, one entrance per chart (a bar or line drawn in 400 ms once, reduced-motion aware) is
the motion that would make the phone feel alive without a second continuous motion (`themes.md` §6).

## What this branch fixed

- T11: Money names each place once (`phone/money.html`).
- A1: one face for Arabic figures and separators (`fonts/fonts.css`, `style.css`, regenerated `style.rtl.css`).
- A2: Arabic transfers read from the first account (`phone/partials/txn.html`).
- Tests: `tests/test_phone_frame.py::test_money_names_each_place_once_and_arabic_transfers_read_from_the_first_account`,
  `::test_arabic_digits_and_their_separators_come_from_one_face`.

## Plan and order

1. **Play blockers, in order:** NF-11B1 (release AAB, API 36, predictive back, no probe), NF-11B3 (no buy link in the Play build),
   NF-11B4 (the app's privacy notice, both repos), NF-11B2 (SMS: ship without `READ_SMS` first, or declare it), NF-11B6 (Recents,
   notifications in context), NF-11B5 and the owner's 11B7-11B9 (Console, listing, closed test).
2. **The phone's look before the listing screenshots:** IV-11E (Home reads at a glance), IV-11D (charts), BV-11F, BV-11G, IV-11H,
   IV-11I; then IV-10G for paid themes.
3. Already planned and needed for the listing: IV-3BG (Arabic chevrons, tap polish, status bar), IV-3BK (human dates), IV-3AY13
   (owner's phone check).

## Validation and limits

- Browser evidence only (Chromium at 412 × 892, device scale 2, touch). Fonts, WebView version and Samsung's system fonts on a real
  phone can differ; A1 was confirmed by rendering both faces side by side (`shots/arabic-commas.jpg`).
- `python -m pytest -q tests/test_phone_frame.py tests/test_phone_money.py tests/test_phone_activity.py tests/test_arabic_no_english.py tests/test_phone_transactions.py`: passed.
- Play rules: target API 36 for new apps and updates since 2026-08-31 (developer.android.com target-sdk page and secondary
  summaries); SMS exceptions and the "SMS-based money management" use (Play Console help 10208820, preview 17225965, read through
  search snippets); closed testing 12 testers / 14 days (help 14151465); Payments policy (help, and press on the US and EEA
  programmes). Re-read each in Play Console when filing; they change often.

## Dated follow-ups

None yet.
