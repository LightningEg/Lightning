---
title: Import review asks the file's few questions instead of showing every row
type: feature
pillar: capture
size: L
model: opus
status: ready
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
Plan only (owner); build nothing until the owner says so (NOW.md, 2026-11-07: "NF-7AB flow plan waits for the
owner"): 7AB7 asks first.

2026-11-08: verified against the code. Already built, so the steps reuse them and do not rebuild:
- partial posting: `confirm` (`lightning/ui/routes/bank_imports.py` ~577) posts resolved rows and keeps the rest as
  `REVIEW` (`tests/test_import_review_rows.py::test_post_ready_rows_leaves_unresolved_rows_for_retry`);
- a waiting list "is waiting for you · Continue the review" on `/import` (`lightning/ui/templates/import.html` line 5,
  `BankImportService.waiting_all`), but not on the account page;
- paged review (IT-7AA8, `REVIEW_PAGE_ROWS = 150`, `GET /accounts/{id}/import/{batch}/groups`);
- "Your file's categories" set once for all rows (IT-7Z, `labelcat` in `confirm`; `file_labels` in `_render_review`);
- Undo of a whole file: `POST /import/{batch_id}/undo` (`lightning/ui/routes/workbench.py` ~43, using
  `BankImportService.created_transactions`), offered only in `/import`'s history, not on the result screen;
- the statement's balance check `balance_gaps` (`lightning/import_reconcile.py`), shown before posting only.

## Decided

- 2026-11-08, owner (7AB7): (1) question cards first, rows only inside an opened card, "See every row" one link away; (2) build it now, in the order under Fix; (3) "Biggest first" with one button that sends every remaining row under a typed amount to Uncategorized.

## Fix

After the owner's pick in 7AB7: 7AB1 and 7AB3 (they replace the row page's first screen; rows load per opened
question group through the existing `/groups` route), then 7AB2, 7AB6, 7AB4, 7AB5. One PC and one phone check by the
owner when 7AB1-7AB3 work end to end. The review page is one template for PC and phone
(`lightning/ui/templates/bank_import_preview.html`, `partials/bank_import_groups.html`); keep it so.

## How to work on this item

Each step is one pull request. Read only the files a step names (the route file is long: `grep -n` the function).
Run the step's test command, then `python -m pytest tests/test_bank_imports.py tests/test_import_review_rows.py
tests/test_issues.py -q`; for a visible change also `python -m pytest tests/test_mohab_year.py -q` and check A16.
New visible words get Arabic in `lightning/ui/i18n.py` `ARABIC_UI`. Delete the step's heading in the same commit.


## 7AB1 Summary first, rows last · M · opus
Needs 7AB7 merged first.
Files: `lightning/ui/routes/bank_imports.py` (`_row_status` ~295, `_render_review` ~389, `preview` ~445,
`more_groups` ~454, `confirm` ~577, `_decision` ~491, `_ready_decision` ~550), `lightning/ui/templates/bank_import_preview.html`,
a new `lightning/ui/templates/partials/bank_import_summary.html`, `lightning/ui/i18n.py`.
Do: (1) `_render_review` passes `cards`: counts per `_row_status` (`ready`, `needs`, `dup`, `err`) and the batch's
skipped count from `c.bank_imports.summary`. (2) The page, when the batch is not POSTED, shows the summary partial
first: one card per non-zero count with its button, and no `.import-line` rows; "Place them", "Check them" and
"See why" open the rows of that state by fetching `/groups?start=0&state=<state>` into the card (add a `state` query
filter to `more_groups`, filtering `_review_pieces` by `g["status"]`). (3) A new `POST /{account_id}/import/{batch_id}/post-ready`
builds decisions with `_decision({}, row)` for rows whose `_row_status(row) == "ready"` and `_ready_decision` passes,
calls `c.bank_imports.confirm(batch_id, decisions)` inside `settled_save`, and re-renders the summary with the flash
`confirm` uses. A "See every row" link (`?rows=all`) keeps today's page.
Done when: new tests in `tests/test_import_review_rows.py`: a file of 3 ready rows, 1 unknown name and 1 duplicate
renders `.import-summary` with 3/1/1 and no `.import-line`; `POST .../post-ready` posts exactly 3 and leaves 2 in
REVIEW; `GET .../groups?state=dup` returns only the duplicate row. `python -m pytest tests/test_import_review_rows.py -q`.

## 7AB3 Group by the question, not the name · M · opus
Needs 7AB1 merged first.
Files: `lightning/ui/routes/bank_imports.py` (`_review_groups` ~341, `_review_pieces`, `more_groups`),
`lightning/ui/templates/partials/bank_import_groups.html`, `lightning/ui/templates/bank_import_preview.html` (the
"Your file's categories" `<details class="import-labels">` block).
Do: inside an opened card, group by question instead of name: "No category: <file label>, N rows" (rows with
`_file_label` and no category), "Which account?" (`_needs_account`), "Possible duplicate", "To fix", then by name for
the rest. Each group header carries one answer control (category select for a label, account select, the
duplicate choice) that writes every row of the group, reusing the `labelcat` field `confirm` already reads for labels
and the bulk bar's script for the others. The separate "Your file's categories" list goes (absorbed, IT-7Z).
Counterparty grouping stays as the existing name filter.
Done when: a test in `tests/test_import_other_app_exports.py` (its `ROWS` have two `Daily Expenses` rows) opens the
needs card and finds one group "Daily Expenses · 2"; posting with one category for it posts both rows in that
category. `python -m pytest tests/test_import_other_app_exports.py tests/test_import_review_rows.py -q`.

## 7AB2 Post in rounds, continue from the account · S · sonnet
Needs 7AB1 merged first.
Files: `lightning/ui/templates/partials/bank_import_summary.html` (from 7AB1), `lightning/ui/routes/register.py`
(`page` ~497), `lightning/ui/templates/register.html` (the account actions, lines ~57-59),
`lightning/ui/templates/phone/register.html`, `lightning/bank_imports.py` (`waiting_all` ~72, `summary` ~426), `lightning/ui/i18n.py`.
Do: the summary shows "{done} of {total} done" where done = posted + linked + skipped + duplicates from
`c.bank_imports.summary(batch_id)` and total = the batch's row count. `register.page` passes
`waiting = [w for w in c.bank_imports.waiting_all() if w["account_id"] == account_id]`; both register templates show,
above the list, a link "Continue import ({n} left)" to `/accounts/{id}/import/{batch_id}` for each.
Done when: a test in `tests/test_import_review_rows.py` posts the ready rows of a 5-row file with 2 unresolved and
finds "3 of 5 done" on the review and "Continue import (2 left)" on `/accounts/{id}`.
`python -m pytest tests/test_import_review_rows.py -q`.

## 7AB6 Safe to go fast: Undo and the balance on the result · S · sonnet
Needs 7AB1 merged first.
Files: `lightning/ui/templates/bank_import_preview.html` (the `{% if batch.status == 'POSTED' %}` card, line ~19),
`lightning/ui/routes/bank_imports.py` (`_render_review`: `balance_gaps` is passed only when not POSTED),
`lightning/ui/templates/import.html` line 21 (the Undo form to copy).
Do: on the "Import complete" card add the same Undo form as `import.html` line 21 (`POST /import/{{ batch.id }}/undo`,
`data-confirm-delete` with the same sentence) when `c.bank_imports.created_transactions(batch_id)` is non-empty (pass
its length as `undo_count`), and show `balance_gaps` after posting too (drop the `!= "POSTED"` condition).
Done when: a test in `tests/test_import_review_rows.py` posts a file and finds the undo form on the result; posting
to it removes the created entries. `python -m pytest tests/test_import_review_rows.py -q`.

## 7AB4 Smart buttons on a group · M · sonnet
Needs 7AB3 merged first.
Verify first: IT-7Z already gives a name the category it got last time (the `remember_` field and counterparty default
category); stage the same file twice and see whether the second review's rows are already Ready. If yes, drop
"Same as last time" below.
Files: `lightning/ui/templates/partials/bank_import_groups.html`, `lightning/ui/routes/bank_imports.py`
(`_review_groups`), `lightning/rules/service.py` (`save` ~159, `name_categories` ~77), `lightning/ui/i18n.py`.
Do: on a question group: "All of these → <category>" sets the group's category and ticks `remember_` for its rows
(that already makes the name's default); "Make it a rule" links to `/rules/new?counterparty=<name>&category_id=<id>`
(check the rules route's query names with `grep -n "query_params" lightning/ui/routes/rules.py`); "Biggest first"
sorts the group's rows by absolute amount in `_review_groups` when `?sort=amount`.
Done when: a test stages a file, answers one group with "All of these" and posts; a second file from the same source
has every row Ready with no per-row edit. `python -m pytest tests/test_import_review_rows.py -q`.

## 7AB5 Quick mode for leftovers · M · sonnet
Needs 7AB3 merged first.
Files: `lightning/ui/static/app.js` (a new `quickReview` block; follow the keydown handler at ~101),
`lightning/ui/templates/partials/bank_import_summary.html`, `lightning/ui/static/style.css` (append one rule set),
`lightning/ui/i18n.py`.
Do: a "Quick mode" button on the needs card shows one `.import-line` at a time with its three suggested categories
(the first three options the row's select already marks as suggested) as buttons 1-3. Keys: Enter accepts the
selected suggestion, 1-3 pick, S ticks Skip, ← goes back; each answer writes the row's existing `category_<id>` /
`skip_<id>` fields, so posting is unchanged. On the phone the same buttons are full width, 52px (Part C).
Done when: new browser test `tests/test_import_quick_mode_browser.py` (profile set-up as in `tools/phone_check.py`
lines 70-97) answers 5 rows with 1, Enter, S, 2, Enter and posts; the 4 non-skipped rows post with those categories.
`python -m pytest tests/test_import_quick_mode_browser.py -q`.
