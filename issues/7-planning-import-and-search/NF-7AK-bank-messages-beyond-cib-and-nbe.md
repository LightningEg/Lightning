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

## Built
2026-11-10: 7AK1 (English card messages: `parse_sms` English pattern, `sure=False` until a real sample confirms it;
an available limit is not a balance) and 7AK2 (wallets: `wallet_key`, the sender is the key, `wallet-<sender>`,
asked once on From SMS as "Wallet <name>"). Tests: `tests/test_sms_imports.py`.

## 7AK3 Purchases in another currency · M
**Owner, 2026-11-09:** a dollar payment is recorded in dollars, and the balance is rated in pounds. The entry keeps
its own currency and amount; the account's balance and the reports convert it at the dated rate (NF-7E's
cross-currency leg), and the bank's later pound debit settles it rather than adding a second expense. Until this
step is built, IV-7AJ keeps the message for the person.

## 7AK4 Use the researched formats · M
`lightning/egypt_bank_sms_formats.json` (941 lines, 35 banks) is loaded by nothing (`currently_loaded_by_parser: false`).
Promote a format to the parser only with a real sample and a test; delete what stays unverified so the file does not
read as coverage. The SMS page's line "CIB and NBE are read today" then lists what is truly read.
