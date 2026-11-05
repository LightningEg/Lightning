---
title: Bank SMS to the ledger takes one trip per card ending and ends on the CSV import screen
type: polish
look: visual
pillar: capture
size: M
status: ready
created: 2026-11-05
by: Claude
---

## Report
The owner (2026-11-05): "the SMS flow is not polished". Twelve real-format messages (eight CIB and NBE samples from
`tests/fixtures/bank_sms.json`, a reworded one, an unreadable one, a code and an offer) were pasted into From SMS on the demo
household, phone at 390 px and PC at 1366 px. Reading is right: 9 read, 1 kept, 2 skipped. Everything after reading was rough:

1. **One trip per card ending.** Four "Which account ends with …?" cards, each with its own Primary; answering one jumped to a
   review of that ending's rows alone (often one row), then back for the next.
2. **The review is the CSV screen.** "Review import" under the Accounts tab, the batch named "SMS 2026-11-05 08:56", "1 row ·
   1 name", Held for, Fee inside this amount, a "Transfer across currencies" panel on an EGP row, Post ready rows twice, and
   never the message itself to check a row against.
3. **An ATM withdrawal arrived with a red error** ("The category says internal, but no account matches") whenever there was
   more than one wallet: `_cash_account_name` named a wallet only when exactly one existed.
4. **The picker did not guess.** It offered every bank and wallet for a CIB card and chose nothing, though the message names
   its bank.
5. **On the phone the answer was below the fold** (A16 lead first): an empty paste box led while 9 messages waited, and the
   result line ran three lines with semicolons over the first card.
6. **Kept messages led nowhere.** Phone "Enter it" opened a blank Add; the PC had no Enter it; the PC promised "Send the
   unread ones to be added as a bank pattern" with no button.
7. **Back went two ways**: From SMS to More, its review to Accounts.

## Fix
Done in this item's first change (S1 and S3, `tests/test_sms_imports.py`):

- **S1 One question for every ending.** `SmsImportService.assign_many` answers them together, one batch per account;
  `/sms/assign` takes `account_<ending>` fields (the single `ending` + `account_id` still works). `guess` chooses the account
  whose saved last four are the ending, else the only account of the bank that sent the messages; another bank's card is
  never guessed. `choices` lists bank accounts first and leaves cash at hand out. One Primary: "Review N messages", or "Save
  and review" while an ending has no likely account.
- **S3 Small fixes.** An ATM withdrawal goes to the cash-at-hand wallet, else the only wallet, else the wallet that took most
  transfers from your banks in the last year. The phone page leads with what waits and folds Paste below it. The result is one
  line ("9 need their account · 1 kept for you · 2 skipped"); a paste that lands on one known account opens its review. Enter
  it (phone and PC) opens Add filled from the message (`prefill`: amount, way, day, the message in Notes); saving it takes the
  message off From SMS (`mark_seen`). The unbuilt "send as a bank pattern" line is gone.

## 3AU2 An SMS review, not the CSV review · M
The bank import review in an SMS mode when its batch came from SMS: titled "Check N bank messages", each row with its message
text under the fields, Held for, Fee inside this amount and the currency panel hidden unless they apply, one Primary "Post N",
and back always to From SMS (point 7). Done when a phone and PC screenshot show it and `tests/test_phone_sms.py` covers the
SMS mode.
