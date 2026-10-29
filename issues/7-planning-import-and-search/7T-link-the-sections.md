---
title: Link the sections - salary-day cascade and a reserve tied to its bill
type: feature
area: planning
status: new
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

7T1 to 7T4 are built (branch `claude/linked-sections`, `lightning/workflows/linked.py`, `tests/test_linked_sections.py`): one transaction page with what it touched, `/counterparties/{id}`, what depends on an account, `/tags/{tag}`. Architecture › Linked sections. What is left needs 7L2 and the owner's calls on 7M and 7R. Every figure is computed in a Python service; plans move no money.

## 7T5 Salary-day cascade

When the real salary settles its planned income, Needs you shows bills before next payday, reserves to refill, goal top-ups and safe to spend, opening the payday allocation filled in (`workflows/salary_setup.py`, `planning/funding.py`). Builds with 7L2.

## 7T6 A reserve tied to its bill

Nullable `cash_reserves.planned_item_id`; the bill shows how much is saved, paying it draws the reserve. Waits for the owner's calls on 7M and 7R.
