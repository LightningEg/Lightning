# Audit 17: logging entries - the Add sheet, bank messages and the way in from a file

Date: 2026-11-09 · Author/reviewer: Claude
Repository: app · Reviewed commit: 90f01900587841fa8fdea859fbf9f2cc8314140a
Code: r31 · App version: 2.1.2

## Assessment

Typing an expense on the phone is already good: amount, a category chip, Save; a known payee fills its category, and
the toast says what is left in that budget. What holds logging back is the automatic side. Bank messages are read
well only for CIB and NBE in Arabic; English card messages, wallets and dollar purchases, which are a large share of
what people receive, fall to manual entry or vanish. And the quick manual path has three gaps: it does not start on
the amount, it refuses an entry without a category, and it cannot repeat.

Order that matters: fix the wrong amount (S1) and the paste that says "no amount" (S2); then widen what messages are
read (S5-S8); then the three owner-chosen features (F1-F3).

## Scope and method

Question: how does a person get an entry in, by hand, from a bank message and from a file; what fails, and what would
make it smarter? Sample household on throwaway encrypted profiles, date 2026-11-09, PC at 1366 x 768 and the phone app
at 390 x 800, driven by Playwright through the real forms ([flows/](evidence/flows/): `python host.py hosts.json`,
two Chromium instances on debug ports 9333 and 9334, `node login.js`, then `p3.js`, `p5.js`, `c2.js`, `c3.js`). The SMS
reader was also run directly on 18 messages: `python issues/7-planning-import-and-search/r31-logging-entries/evidence/sms_battery.py`
([output](evidence/sms_battery.txt)). File import was looked at as a journey only: r23 stress-tested it four days
ago and NF-7AB plans its review.

## Findings

Severity: high = wrong money or a lost entry; medium = a job that takes the long way; low = polish.

### Bank messages

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| S1 | high | A message written with the Arabic decimal mark is read as the wrong amount: ١٤٧٫٨٧ becomes 87. | Fixed: `tests/test_sms_imports.py::test_arabic_decimal_and_thousands_marks_read_as_the_right_amount` |
| S2 | high | Phone, Add › Paste SMS on an English card message says "No amount found in this message." though EGP 250.00 is in it; the PC's *Enter it* finds it. [Screenshot](evidence/phone-paste-english-card.png). | IV-7AJ |
| S3 | medium | *Enter it* opens Add dated today with no payee, though the message says 08/11/26 at TALABAT. | IV-7AJ |
| S4 | high | A dollar purchase ("charged USD 12.99 at NETFLIX.COM") is "1 skipped": not read, not kept, no trace. [PC after paste](evidence/pc-sms-after-paste.png). | IV-7AJ, NF-7AK3 |
| S5 | medium | English card messages ("was charged", "was used for", "You spent") are not read: the out-words do not include them. | NF-7AK1 |
| S6 | medium | Wallet messages (Vodafone Cash paid, received) are never read: they carry no four-digit ending, which the general rule requires. | NF-7AK2 |
| S7 | medium | Only three wordings have a named pattern (CIB and NBE card, InstaPay, CIB salary). Everything else is the general rule, marked "check this", often with no shop (refund, Fawry bill, ATM). | NF-7AK4 |
| S8 | low | `egypt_bank_sms_formats.json` (941 lines, 35 banks) is loaded by nothing; it reads as coverage that does not exist. | NF-7AK4 |
| S9 | medium | Every message waits for review, and a shop needs its category chosen again in review ("CARREFOUR MAADI · Needs you") unless a rule exists. | NF-7AO, NF-7AB |
| S10 | low | The shop's raw text becomes the payee ("UBER *TRIP HELP.UBER.COM"). Known from r23 C3. | NF-7AB |
| S11 | low | The balance each message states ("المتاح 3792.36") is read and stored but never compared with the account's balance; it could flag a missed entry the same day. | NF-7AP |

### Typing an entry

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| A1 | medium | Phone Add opens with the focus on the Out/In/Move radio, not Amount (r27 J1, still there). The PC register opens with no focus at all. [Sheet](evidence/phone-add-sheet.png). | IV-7AL, IV-3BF4 |
| A2 | medium | After Save the phone shows a different home ("Overview", month picker, "4 items need you") at the same address as "Home". [Screenshot](evidence/phone-after-save.png). | IV-7AL |
| A3 | low | *From* offers the CD portfolio, the gam'eya and the broker; the default is the last account used, not the one this payee is usually paid from. | IV-7AL |
| A4 | low | A missing category shows the browser's bubble over the list. [Screenshot](evidence/phone-amount-only.png). | IV-7AL, IV-3BF5 |

### What works

- Phone Add: one sheet over any page, Out/In/Move, category chips from use, payee suggestions, a known payee fills
  its category, the toast says "Utilities & Bills: 1,010 left this month" with Undo.
- A known-pattern message pasted on the phone fills amount, payee and date and asks once which account ends 1234.
- Codes, declined payments and offers are skipped; unreadable messages with money are kept, never dropped (S4 apart).
- Pasting a batch on the PC groups by card, remembers the card's account, and the review shows each message beside its row.
- The same message twice is skipped by its fingerprint. Sharing a message into the app exists on Android.

### Features considered

| ID | Feature | Owner, 2026-11-09 | Follow-up |
| --- | --- | --- | --- |
| F1 | Repeat an entry in one tap; Save and add another; usual payees as chips | Build | NF-7AM |
| F2 | Save with only an amount, sort later | Build | NF-7AN |
| F3 | Messages Lightning is sure about save themselves, marked and undoable | Build ("auto-save the sure ones") | NF-7AO |
| F4 | App notifications (Telda, InstaPay, wallets) as a source | Not chosen | none |
| F5 | A receipt photo on an entry | Not chosen | none |

## Validation and limits

Browser evidence on sample data; the full suite was not run because no code changed. The 18 messages are written to
resemble common wordings and are not verified bank text: they show which shapes the reader handles, not which banks.
Not checked: the Android app itself (reading the inbox, the permission question, share-into, the keyboard), Arabic
screens, transfers and money in on the Add sheet, editing an entry, the PC register's new row beyond its focus, rules,
recurring bills, file import beyond its entry page (see r23), synchronized profiles.

## Dated follow-ups

- **2026-11-09, owner decisions (question dialog).** Add to the plan: F1 and F2. SMS: auto-save the sure ones (F3),
  which replaces "nothing is posted without review" for those messages only; NF-7AO1 defines "sure". F4 and F5 were
  offered and not chosen. S11 (balance check) has no item; raise it when NF-7AO is built.

- **2026-11-09, owner decisions, second round (question dialog).** A dollar payment is recorded in dollars and the balance is
  rated in pounds (NF-7AK3). The balance a message states is compared with the account as a quiet To do row (S11, NF-7AP).
