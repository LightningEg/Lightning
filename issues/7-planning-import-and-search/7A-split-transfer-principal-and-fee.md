---
title: Import cannot split a transfer into principal and fee
type: feature
pillar: capture
size: M
status: ready
post: no
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

**Not posted to contributors (2026-10-31):** the owner deferred it on 2026-10-15 (build it if a second user asks) and it is large.
