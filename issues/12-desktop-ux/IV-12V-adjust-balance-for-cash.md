---
title: Adjust balance: show the account's last rows beside the form
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
[r34](r34-accounts-and-transactions/report.md) B1-B3. Evidence: [small difference](r34-accounts-and-transactions/evidence/pc-adjust-small.png), [too big](r34-accounts-and-transactions/evidence/pc-adjust-too-big.png).
- A small difference (within 1% of the balance, at least 100) is handled well: "Post adjustment of −75.00" or *Review
  rows instead*.
- Cash wallet 10,975 against 9,000 counted: "Too big to adjust ... Review 2026-11 row by row · Import the statement
  again". A wallet has no statement; the person stops here. An *Unaccounted Spending* category already exists.
- The adjustment is filed as "Other Personal spending", inside the budget, where it reads as a purchase.
- The page is a date and a number with no account context; "Lightning shows 83,393.36" keeps piastres.

## Fix
Built: any size on cash and wallet accounts, filed under Unaccounted Spending or Unaccounted Money Found; bank accounts keep the limit. Left: the page shows the account's last rows beside the form. Test: the page lists them.
