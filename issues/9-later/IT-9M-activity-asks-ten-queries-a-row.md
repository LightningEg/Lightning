---
title: Activity on the PC asks ten queries for each of its 100 rows - 1,039 queries where the budget is 400
type: tech
pillar: understand
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
---

## Report
Found by [r31](../1-easy-to-contribute/r31-code-review-and-loose-ends/report.md) F3. `GET /activity` (PC) asks 1,039 queries on the sample. `lightning/workflows/activity.py:ActivityReview.recent` (line 29) finds 100 ids and calls `self.summary(id, include_choices=False)` for each. Every call asks, once per row:

`SELECT * FROM transactions WHERE id = ?` · its ledger lines · `SELECT 1 FROM money_from_others ...` · the bank-import source rows · the planned payments · the reserve links · `SELECT 1 FROM sqlite_master ...` (`has_table`) · `SELECT id FROM reimbursement_claims WHERE expense_id=?` · the counterparty identity read.

The list (`lightning/ui/templates/activity/index.html`) shows only: the transaction, account names, category names, amount, currency, and three yes/no marks (planned, reserve linked, claim).

## Fix
Files: `lightning/workflows/activity.py` only (`recent`, plus one new private method); read `summary` and `_owned_cash` in the same file. Do not change `summary`: the transaction page (`lightning/ui/routes/transactions.py:519`) uses it for one row.

1. Add `_list_rows(self, ids: list[int]) -> list[dict]` that returns, for the list only, dictionaries with the keys the template reads: `txn`, `account_names`, `currency`, `amount`, `category_names`, `planned_links`, `reserve_links`, `claim` (the last three may be truthy placeholders such as `[1]`/`{"id": n}`: the template only tests them), and any other key `index.html` or `templates/phone/activity/index.html` reads (grep `row\.` in both first).
2. Inside it, load in bulk with `WHERE ... IN (?,?,...)`: transactions through the existing bulk reader if the service has one (`grep -n "def get_many\|def list_by_ids\|IN (" lightning/transactions/repository.py`), else `self.c.transactions.get` stays per row for now; then one query each for: ids with a planned payment or loan extra payment, ids with a reserve link, ids with a reimbursement claim (call `self.db.has_table("reimbursement_claims")` once, before the loop).
3. `recent` returns `self._list_rows(ids)`.

Test: in `tests/test_reporting_performance.py` (copy its query-counting pattern): render `/activity` on the sample before and after and assert the HTML is identical (strip the session token as that file does) and the query count is under 400. Run `python -m pytest tests/test_activity*.py tests/test_reporting_performance.py -q` and Mohab.

## Done when
`/activity` asks fewer than 400 queries (aim under 250) with byte-identical HTML on the sample, PC and phone. `Detail:` carries the before and after counts. Release-note: none.
