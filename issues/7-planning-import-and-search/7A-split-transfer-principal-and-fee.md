---
title: Import cannot split a transfer into principal and fee
type: feature
area: import
status: ready
created: 2026-10-15
by: Claude Sonnet 5.5
skills: feedback-review
app_version: 1.1.0b1
commit: c4f6378
repo: app
---

## Report
A bank statement shows a transfer and its fee as one row; users want it posted as the transfer plus a fee expense (feedback batch 002, row 32).
`TransactionService.update_expense_split` handles ordinary expenses only. Owner decision 2026-10-15: deferred; build it if a second user asks. Large: touches the import review, the split rules and the register. Severity: low.
