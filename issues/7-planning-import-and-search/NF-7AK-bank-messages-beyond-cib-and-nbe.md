---
title: Bank messages beyond CIB and NBE in Arabic: English card messages, wallets, other currencies, and the researched formats
type: feature
pillar: capture
size: L
model: opus
status: new
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r31](r31-logging-entries/report.md) S5-S8. Of 18 dummy messages ([battery](r31-logging-entries/evidence/sms_battery.txt)), 3 match a
named pattern, 6 are read by the general rule (to check) and 6 real payments are not read. The messages are written to
look like common wordings; they are not verified bank text, so each step starts from real samples (owner or
contributors, sanitized into `tests/fixtures/bank_sms.json`).

## 7AK1 English card and account messages · M
"was charged", "was used for", "You spent" are not in the out-words, so English CIB debit and credit card messages
and Telda are unread. Add the words and a named English card pattern; a credit card's "available limit" is not a balance.
**Done when:** the battery's English lines read with shop, date and ending.

## 7AK2 Wallets, which name no card ending · M
Vodafone Cash and other wallets say "محفظتك" and no four digits; the general rule demands an ending, so every wallet
payment is manual. Let a sender (or the word wallet with its brand) be the account key, asked once like a card ending.
**Done when:** a wallet payment and a wallet receipt stage rows in the wallet account.

## 7AK3 Purchases in another currency · M
See IV-7AJ for keeping them; this step reads them into the account in their own currency (or as a cross-currency leg,
NF-7E's model) so the later EGP debit is not a second expense. Money logic: design first.

## 7AK4 Use the researched formats · M
`lightning/egypt_bank_sms_formats.json` (941 lines, 35 banks) is loaded by nothing (`currently_loaded_by_parser: false`).
Promote a format to the parser only with a real sample and a test; delete what stays unverified so the file does not
read as coverage. The SMS page's line "CIB and NBE are read today" then lists what is truly read.
