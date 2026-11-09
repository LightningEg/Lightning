# Google Play: what to put in the Console

For the owner. Each answer comes from the code, with the file that proves it, so the Console can be filled from this
page alone. The plan is [NF-11B](../issues/11-phone-ux/NF-11B-ship-the-phone-on-google-play.md); the audit behind it is
[r29](../issues/11-phone-ux/r29-google-play-readiness/report.md). The Data safety and other declarations come with 11B5.

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
