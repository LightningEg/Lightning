---
title: PC ledger noise - each transfer is two rows, the save message shows an internal reference and cents, and Mark paid has no Undo
type: polish
pillar: capture
size: M
status: new
created: 2026-11-06
by: Claude
---

## Report

Audit r26 F8 ([report](r26-user-test-pc-and-phone/report.md)). In Transactions' Every account view a transfer shows as two rows (From… +2,000 and To… −2,000): 10 of the first 50 rows on the sample. Saving a transaction says "Saved OUT-2026-11-06-002. Budget · Shopping: 999.00 EGP left this month" (an internal reference, and cents on a budget figure). Cash planning's "Record and mark paid" toast has no Undo, while the phone's message carries one (`partials/history.html`).

## Fix

Every account view: one row per transfer ("CIB Payroll → Office gam'eya", unsigned, as the phone shows it), both halves still visible inside one account. Save message: "Saved. Shopping: 999 left this month." The PC toast after Mark paid carries the same Undo as the phone. Tests: register row count for a transfer in the all-accounts view; the message text; Undo restores the bill.
