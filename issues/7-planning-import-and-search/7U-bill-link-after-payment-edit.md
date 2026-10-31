---
title: Editing a paid bill's transaction keeps the bill paid at the old amount and date
type: bug
look: technical
severity: low
pillar: plan
size: S
status: new
created: 2026-10-29
by: Claude
skills: number-audit
app_version: 1.5.1
commit: 045ccd4
repo: app
---

## Report

Found by the [use-case audit](../../reports/2026-10-29-use-case-audit/report.md) (F3). Record a 500 Internet bill as paid on 2026-02-05, then edit that transaction to 5,000 on 2026-12-05: February stays PAID for 500, bills due on 2026-02-28 read 0 though no money left until December, and December shows the moved payment and its own bill still due. Three links behave three ways after the linked transaction is edited: a loan payment refuses the edit until reopened (`TransactionService`, Architecture › Action history), a reserve link is removed (7R), a bill or income link keeps the stored `planned_payments.amount_e6` and counts as paid on any date (`PlanningRepository.settled`; only loans skip a payment whose transaction is dated later).

## Fix

Owner decision with 7R: one rule for every link when its transaction's amount, date or account changes. Proposal: keep the link while the edited transaction still fits the item's match window and tolerance, refresh the paid amount from the transaction, treat a payment as unpaid before its transaction's date (as loans do), and otherwise unlink it and say so on Save.
