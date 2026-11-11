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
2026-11-11: 7AK4: `lightning/egypt_bank_sms_formats.json` deleted. Of its 9 formats, 7 were the CIB and NBE wordings
the parser already reads and 2 unverified demos; its other 33 banks had none. The research stays in Git history
(`git show a996dbb3:lightning/egypt_bank_sms_formats.json`); a new bank is added to `sms_imports.py` from a real sample with a test. The SMS page's
"CIB and NBE are read today" was already true.

## 7AK3 Purchases in another currency · M
**Owner, 2026-11-09:** a dollar payment is recorded in dollars, and the balance is rated in pounds. The entry keeps
its own currency and amount; the account's balance and the reports convert it at the dated rate (NF-7E's
cross-currency leg), and the bank's later pound debit settles it rather than adding a second expense. Until this
step is built, IV-7AJ keeps the message for the person.
