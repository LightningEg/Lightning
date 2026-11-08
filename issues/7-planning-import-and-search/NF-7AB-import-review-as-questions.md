---
title: Import review asks the file's few questions instead of showing every row
type: feature
pillar: capture
size: L
model: opus
status: new
created: 2026-11-05
by: Claude Opus 5.5
skills: feedback-review
---

## Report

The owner's 377-row file held about four decisions (262 rows already right, ~12 category names to place, 12 possible
duplicates, 4 balance rows), but the review showed 377 rows of seven fields each, grouped by counterparty
([feedback FB1](../../feedback/2026-11-05-csv-import-and-phone-update.md),
[stress test](r23-csv-import-stress/report.md) D4–D5: 25 MB page at 5,000 rows).
Owner, 2026-11-05: "300 rows is unusual; do something with the flow: better module, smarter buttons and features."
Plan only (owner); build nothing until the owner says so.

## 7AB1 Summary first, rows last · M
After upload, one screen of cards: *N ready* [Post them], *N names to place* [Place them], *N possible duplicates*
[Check them], *N skipped* [See why]. Rows render only inside an opened card. Done when: the owner's file posts its
ready rows in one click from the first screen.

## 7AB2 Post in rounds · S
"262 of 377 done" progress; what is left waits as "Continue import (115 left)" on the account page. Partial posting
already exists (`test_post_ready_rows_leaves_unresolved_rows_for_retry`); the flow leads with it.

## 7AB3 Group by the question, not the name · M
Groups are what is missing: "No category: Daily Expenses, 49 rows", "Possible duplicate", "Which account?". Each
group answers once for all its rows; counterparty grouping stays as a filter. Absorbs the "Your file's categories"
list (IT-7Z).

## 7AB4 Smart buttons on a group · M
*Same as last time* (the category this name got before), *All of these → category* then *Make it a rule*, and
*Biggest first* (sort by amount; small leftovers take one Uncategorized). Done when: a repeat file from the same
source posts with no per-row edits.

## 7AB5 Quick mode for leftovers · M
One row at a time: Enter accepts the suggestion, 1–3 picks one of three suggested categories, S skips, ← back.
Works with touch on the phone (Part C wins there). Done when: 20 leftover rows take under a minute by keyboard.

## 7AB6 Safe to go fast · S
The result screen carries *Undo this import* (the batch's created entries, already available as
`created_transactions`) and, with the balance check built in IT-7AA9 (`lightning/import_reconcile.py`) against the statement.

Order: 7AB1–7AB3 together (they replace the row page; rows load per opened group, which also fixes the page size in
IT-7AA8, built: `REVIEW_PAGE_ROWS` and `/import/{batch}/groups`), then 7AB4, 7AB6, 7AB5. Needs one PC and one phone check by the owner when 7AB1–7AB3 work end to end.
