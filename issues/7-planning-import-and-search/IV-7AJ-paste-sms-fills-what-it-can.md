---
title: A message in another currency (USD) is kept for you, not dropped
type: polish
pillar: capture
size: S
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
[r31](r31-logging-entries/report.md) S2-S4. Evidence: [phone paste](r31-logging-entries/evidence/phone-paste-english-card.png).
- **Phone, Add › Paste SMS.** "Your debit card ending with 1234 was charged EGP 250.00 at TALABAT on 08/11/26" answers
  "No amount found in this message." The amount is there: `/sms/read-one` asks only `parse_sms`; `prefill()` (which
  finds 250.00 and "out") is used by the PC list's *Enter it* but not by this button.
- **Enter it** (PC and phone, messages kept for you) opens Add with today's date, though the message says 08/11/26, and
  with no payee, though it says "at TALABAT".
- **A dollar purchase is dropped.** "charged USD 12.99 at NETFLIX.COM" is counted as "1 skipped": not read, not kept.

## Fix
Built (7AJ part 1): `read-one` falls back to `prefill`, which now also returns the date and the shop. Left: a message with an
amount in another known currency is kept for you (and prefilled with that currency when the profile has it). Tests: "charged
USD 12.99 at NETFLIX.COM" through `SmsImportService.read`.
