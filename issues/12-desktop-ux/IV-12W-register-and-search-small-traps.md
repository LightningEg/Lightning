---
title: Register and search: the forgotten minus, transactions in PC search, and small things on the rows
type: polish
pillar: capture
size: M
model: sonnet
status: ready
created: 2026-11-10
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: a4f696b
repo: app
---

## Report
[r34](r34-accounts-and-transactions/report.md) T1-T6.
- **Forgotten minus.** In the PC register, Carrefour with 200 (no sign) saves as money in, titled Refund, and the toast
  says "Food & Groceries: 1,615 left this month" (more than before). No question is asked.
- **PC search** for "vodafone" lists actions, the account and the counterparty, then a link "Find transactions with
  vodafone"; the phone lists the payments first. [PC](r34-accounts-and-transactions/evidence/pc-search.png), [phone](r34-accounts-and-transactions/evidence/phone-search.png).
- **Bulk bar** with two rows selected reads "Set category for 0" beside "Delete 2". [Screenshot](r34-accounts-and-transactions/evidence/pc-bulk-bar.png).
- **Notes** is the narrowest column ("Not…") though it is free text; ".00" on every row (also IV-3AM).
- **Zakat** is a tab under Transactions; when it is off the tab opens Settings with a message.
- **Phone account page** shows running balances with piastres (83,393.36) beside whole amounts. [Screenshot](r34-accounts-and-transactions/evidence/phone-account.png).

## Fix
**Owner, 2026-11-10:** ask once on save ("Refund of 200, or a payment?") only when a positive
amount lands on a spending category. PC search shows the first five matching transactions above the other groups.
The bulk bar counts the rows each action will touch and hides an action that touches none. Notes takes the spare
width. The Zakat tab shows only when zakat is on. Whole EGP on the phone's running balance. Tests per bullet.
