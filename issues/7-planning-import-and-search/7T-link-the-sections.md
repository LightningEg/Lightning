---
title: Link the sections - salary-day cascade and a reserve tied to its bill
type: feature
pillar: plan
size: L
status: building
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

7T1 to 7T4 are built (branch `claude/linked-sections`, `lightning/workflows/linked.py`, `tests/test_linked_sections.py`): one transaction page with what it touched, `/counterparties/{id}`, what depends on an account, `/tags/{tag}`. Architecture › Linked sections. The remaining salary-day review and bill reserve are being completed under the owner's delegated report work; 7L2 and the 7M/7R decisions are implemented. Every figure is computed in a Python service; plans move no money.

7T5 is built: a settled salary opens the reviewed payday allocation with bills, reserves, goals and Safe to spend. `tests/test_salary_day_review.py` covers the review and explicit confirmation; no cash is assigned automatically.

## 7T6 A reserve tied to its bill · L

Implemented in `reserves.py`, `planning/service.py`, migration 0073 and the existing Reserves Edit form. One active project reserve explicitly funds one bill or subscription. Bill/payment screens show saved cash; settling draws no more than is available, atomically, with no second cash transaction. Dated snapshots preserve old associations. The bill owns the remaining forecast commitment, so the linked reserve does not add a second goal top-up or suggested payday refill. Existing unlinked profiles keep their results. Gross spending stays visible; plan advice and envelope consumption exclude confirmed reserve coverage. `tests/test_reserve_bills.py` verifies partial/full funding, future/due payments, no change in Safe to spend on payment/void/restore, allocation across occurrences, edits, rollback, undo/retry, migration and real encrypted home/replica replay with different local IDs. Salary-day 7T5 remains under journal validation before this item closes.
