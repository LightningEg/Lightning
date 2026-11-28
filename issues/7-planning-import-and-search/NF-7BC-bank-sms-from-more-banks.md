---
title: Read bank SMS from the next most used Egyptian banks, reviewed before posting like CIB and NBE
type: feature
pillar: capture
size: M
model: sonnet
status: new
created: 2026-11-28
by: Claude
---

## Report
[r41](r41-the-next-big-thing/report.md) phase 2 (owner adopted, 2026-11-27; reading app notifications not adopted for
now). `lightning/sms_imports.py` reads CIB and NBE messages in Arabic only; every Egyptian competitor reads more banks.

## Fix
One tested rule per bank, Arabic and English messages, in the order of how many salaried users hold them (Banque Misr,
QNB, AAIB, Banque du Caire, HSBC to be confirmed by the owner's sample messages). Each message still goes through the
same review before it posts. Done when: `tests/fixtures/bank_sms.json` holds sanitized samples per bank (purchase,
refund, transfer, salary, a one-time code that must be ignored) and `tests/test_sms*` reads each correctly.
Needs: sample messages from the owner or testers, with numbers and names replaced (launch checklist #579).
