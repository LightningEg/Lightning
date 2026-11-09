# Google Play: what to put in the Console

For the owner. Each answer comes from the code, with the file that proves it, so the Console can be filled from this
page alone. The plan is [NF-11B](../issues/11-phone-ux/NF-11B-ship-the-phone-on-google-play.md); the audit behind it is
[r29](../issues/11-phone-ux/r29-google-play-readiness/report.md).

## SMS: the Permissions Declaration (READ_SMS)

Owner, 2026-11-09: declare it from the first release.

| Console question | Answer |
|---|---|
| Permission | `READ_SMS` only. Lightning never sends SMS and does not ask to be the default SMS app. |
| Core functionality | **SMS-based money management.** |
| Why the app needs it | Lightning is a personal budget for salaried people in Egypt. Egyptian banks confirm every card payment, transfer and salary by SMS; Lightning reads those confirmations and turns each into a transaction the person checks before it is saved. Without it, every payment is typed by hand. |
| Is it the core of the app? | Yes. Capturing spending is the core of a budget, and bank SMS are the only record most Egyptian banks send in time. |
| What is read | Messages from senders that are a name or a short code (CIB, NBE, 19623). The query to the SMS provider leaves out every sender that is a phone number, so a person's message never reaches the app (`SmsBridge.java` `NOT_A_PERSON`, tested in `tests/test_sms_imports.py`). Only messages newer than the last read, at most 500 at a time. |
| Where it goes | Nowhere. Messages are read into the person's encrypted profile on the phone and stay there. Lightning has no account, no server for this, and no analytics. |
| When it is asked | Only after the person opens From SMS, where the disclosure is the first thing on the page, and taps **Allow reading SMS**. Saying no leaves the app fully working: paste a message, or Share it to Lightning from the SMS app. |
| Alternatives considered | SMS User Consent and Retriever APIs read one message addressed to the app (one-time codes) and cannot read a bank's confirmations. Paste and Share are kept as the way in without the permission. |

The disclosure on screen (English; Arabic in `lightning/ui/i18n*`):

> Lightning reads the SMS your banks send and turns each payment, transfer and salary into a transaction you check. It
> reads messages from senders with a name or a short code, like CIB or NBE, never from people's numbers. The messages
> stay on this phone: nothing is sent anywhere. Nothing is posted until you check it.

## SMS: the demo video (about 60 seconds)

Record on a real phone with the demo household (no real money on screen); upload unlisted to YouTube and paste the link.

1. Open Lightning, then Money, then **From SMS**. Pause on the disclosure at the top (3 s): it is the first thing shown.
2. Tap **Allow reading SMS**. Android's own question appears; tap Allow.
3. Back on From SMS, the bank messages from CIB and NBE are read: show "Which account is each card?" and pick one.
4. Tap **Review**: each message is a row to check. Save one; show it in Activity.
5. Show the SMS app beside it: a message from a person's number is in the inbox and is not in Lightning.
6. In Android's settings, take the SMS permission away; back in Lightning, Paste on From SMS still reads a message.

## App content

| Console page | Answer | From |
|---|---|---|
| Privacy policy | `https://lightningeg.com/privacy.html` (section 2, *The Lightning App*; Arabic `/ar/privacy.html`). The app links it from Settings › Your data › Privacy. | website `privacy.html`, `entitlements.UPDATE_PATHS` |
| Ads | No ads. | no ad SDK in `build.gradle.kts` |
| App access | **All or some functionality is restricted.** Give reviewers these steps: open Lightning › *Create a profile*, any name and a password of your choice (write it down) › on the welcome page, under *Or explore a sample*, tap **Mohab · A full year**. Every screen then has a year of dummy data. No login, no account, no code. | `dashboard/welcome.html` |
| Content rating (IARC) | Category: utility/productivity (finance). No violence, sexuality, language, controlled substances, gambling or user-generated content shared with others; no location sharing; digital purchases: **yes** (themes). | the app |
| Target audience | 18 and over only. Not designed for children. | owner, r29 |
| News app | No. | |
| Government app | No. | |
| Health | None. | |
| Financial features | **Personal finance: budgeting, expense tracking, net worth.** Not: loans, credit, payments or transfers, banking, crypto, investment advice or trading. The app records money; it moves none. | AGENTS §4 |
| Data safety | See below. | |
| Foreground service | See below. | |

## Data safety

| Question | Answer | Why, from the code |
|---|---|---|
| Does the app collect or share user data? | **Yes.** | the three rows below |
| Encrypted in transit? | **Yes.** Every request is HTTPS; device pairing is pinned TLS. | `entitlements.py`, `market/sources/*`, `sync/journal/discovery.py` |
| Can people ask for deletion? | **Yes.** Uninstall or clear storage deletes everything on the phone; a purchase record is deleted on request (hello@lightningeg.com). No account exists, so no account-deletion URL is needed. | privacy notice §2 |
| Financial info › Other financial info | **Collected and shared**, optional, *App functionality*. When the person updates prices, the tickers and fund names they hold go to Yahoo Finance, TradingView and Mubasher. No amounts or names. Declaring it is the safer answer (r29). | `lightning/market/sources/` |
| Financial info › Purchase history | **Collected, not shared**, required for buying a theme, *App functionality*. The store keeps which theme a Google Play order unlocked (order id and the purchase token's hash only). | website `redeem-play`, `play_purchases` table |
| Device or other IDs | **Collected, not shared**, required for theme unlocks, *App functionality*. The profile's random id (a UUID made by the app, not a device id) names the profile a purchase unlocks. | `entitlements.profile_id` |
| SMS and call log › SMS | **Not collected.** Read and processed only on the phone (Google's on-device exemption). | `SmsBridge`, `sms_imports.py` |
| Messages between your devices | **Not declared**: end-to-end encrypted mail through the Cloudflare relay, which cannot read it (Google's end-to-end encryption exemption). | `sync/journal/cloud.py` |
| Everything else (location, contacts, photos, audio, health, browsing, crash logs, analytics, personal info) | **Not collected.** No analytics or crash SDK. | `build.gradle.kts` |

## Foreground service (dataSync)

| Question | Answer |
|---|---|
| Type | `dataSync` (`SyncService`, `AndroidManifest.xml`). |
| What it does | Only while the person has lent the ledger to their PC, or a pairing is open (never for reminders: those are a periodic job, `ReminderJobService`), Lightning keeps listening on the local network for a few minutes so the PC can hand the ledger back; it shows a notification the whole time and stops itself when nothing needs it or Android's time limit ends it. |
| Why it cannot wait | The hand-back is started by the person on the PC; if the phone stopped listening, the PC's changes could not return until the phone app is opened again. |
| What the person sees | A notification saying what it waits for ("Waiting for your PC to pair", or where the ledger is) until it ends. |

### The video (about 45 seconds)

1. On the PC and the phone, open the same profile (paired). On the phone, Devices › lend the ledger to the PC.
2. Press Home on the phone: the notification appears and stays.
3. On the PC, make one change and hand the ledger back. The phone's notification goes away by itself.
4. Open the phone app: the change is there.

## Other permissions

| Permission | Why |
|---|---|
| `POST_NOTIFICATIONS` | Reminders the person turned on, and the foreground service's notification. Asked when reminders are turned on, never at first start. |
| `USE_BIOMETRIC` | Optional fingerprint unlock (Settings › This phone). |
| `com.android.vending.BILLING` | Theme purchases (Play build only). |
| `INTERNET`, `ACCESS_NETWORK_STATE`, `VIBRATE`, `FOREGROUND_SERVICE*` | Normal permissions; no declaration. |

## In-app products

One managed product per paid theme, product id = theme id: `cotton`, `dendera` (day and night), `nile`, `papyrus`. Name and description from the theme; price set by the owner in Egyptian pounds. One purchase per person (owner, 2026-11-09): a purchase unlocks every profile opened in the Play build with the buying Google account, up to 10, and each profile's other devices through sync. A refunded or voided purchase unlocks no new profile; licences already issued stay.
