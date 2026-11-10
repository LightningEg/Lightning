---
title: Compare the balance a bank message states with the account, as a quiet To do row
type: feature
pillar: capture
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r31](r31-logging-entries/report.md) S11 (owner chose it, 2026-11-09). A bank message often states the balance after the payment
("المتاح 3792.36"). `parse_sms` reads it and stores it, and nothing uses it.

## Fix
After a message's row is posted (or matched to an entry), compare the stated balance with the account's ledger balance
at that moment. When they differ by more than a piastre, Home's To do and the PC's Needs you show one quiet row per
account: "CIB Payroll is 350 off the bank's balance since 7 Nov", linking to that day's entries; it clears when a later
message agrees, or when dismissed (a pending hold makes the bank's figure lag). A credit card's "available limit" is
not a balance. Never adjusts an entry. Tests: agree, differ, later agreement clears, dismissed stays quiet.
