# Import scenarios: a person bringing their real money in

Date: 2026-11-05 · Author/reviewer: Claude (bug-hunt skill, acting as a user)
Repository: app · Reviewed commit: 75d63ae8fb9769efafb8d580fe9254f0532319d3

## Scope and method

The owner imported their own CSV after the 2.0 update and met several pain points, the worst being that every possible
duplicate had to be switched from Skip to "Post as new" one row at a time. The question: **acting as different people,
where does importing get stuck, lose money or make you do work the app could do?**

Five people, each with dummy files (in [evidence/files](evidence/files)), run against the demo (`--demo`, CIB Payroll and
THNDR accounts) over HTTP and in Chromium at 1366×768:

1. **Catching up the bank account** after typing some entries by hand: a CIB-style export of the whole period (Date,
   Description, Debit, Credit, Balance), with two same-day Talabat orders added (`s1_cib_full.csv`).
2. **An Arabic or awkward bank file**: Arabic headers (UTF-8 and Windows Arabic), title lines above the header with total
   rows below, a Dr/Cr marker column (`s2a`-`s2d`), and English bank descriptions (`s2f.csv`).
3. **Moving in from a personal spreadsheet**: one sheet with an Account column, one sheet per account, a running-balance
   formula (`s3a`-`s3c`).
4. **Adding existing investments** at THNDR: the holding form, and a cash statement with buy and dividend lines (`thndr.csv`).
5. **Re-importing** a statement already posted (the batch flags it; works as designed).

`python reports/2026-11-05-import-scenarios/evidence/run_scenarios.py` replays the uploads against a running demo.

## Findings

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | high | A `Dr/Cr` column has nowhere to go in the map step: every debit stays positive. An Uber trip with category Transportation posted as an **IN** of +145.50; no warning that a spending category sat on money in. | `files/s2d_drcr.csv` | 7Z (built) |
| F2 | high | Two genuine same-day orders of one amount (Talabat −245 ×2), with nothing in the books yet, were both flagged "Possible duplicate" and defaulted to **Skip**. Posting with defaults said "Import complete: 0 posted, 44 linked, 2 duplicates": 490 EGP silently left out. Lightning's own AI prompt tells people to keep such rows; the Mohab sample generator nudges amounts to dodge it. | `files/s1_cib_full.csv` | Fixed in this branch |
| F2b | medium | The owner's report: no way to decide many look-alikes at once. The bulk bar had Skip but no "Post as new", and no way to tick all rows a filter shows. | `review-bulk-bar-before.png` | Fixed in this branch |
| F3 | medium | Arabic headers (`التاريخ`, `البيان`, `مدين`, `دائن`) match nothing; every column is mapped by hand. | `files/s2a_arabic_utf8.csv` | 7AA |
| F4 | medium | A CSV saved by Excel on Arabic Windows (cp1256) is refused with "Save the statement as a UTF-8 CSV file". | `files/s2b_arabic_cp1256.csv` | 7AA |
| F5 | medium | Title lines above the header (bank, account number, period) make the bank name the only column: a dead end. Total and closing-balance rows would be rows to fix. | `files/s2c_preamble.csv` | 7AA |
| F6 | low | Common names missed: `Txn Date`, `Narration`. | `files/s2d_drcr.csv` | 7AA |
| F7 | medium | One sheet with an Account column is refused ("Export one account at a time"). | `files/s3a_one_sheet_multi.xlsx` | 7AB |
| F8 | medium | A workbook with one sheet per account is refused. | `files/s3b_sheet_per_account.xlsx` | 7AB |
| F9 | low | A running-balance formula in an unmapped column refuses the whole workbook. | `files/s3c_formula_and_notes.xlsx` | 7AB |
| F10 | medium | Description maps to Notes, not Counterparty: the 46-row statement shows 46 groups all named "No counterparty". | `files/s1_cib_full.csv` | 7AC |
| F11 | medium | `POS PURCHASE CARREFOUR MAADI` is not matched to the saved Carrefour; one shop in two branches makes two groups. | `files/s2f.csv`, `review-bank-descriptions.png` | 7AC |
| F12 | medium | `ATM WITHDRAWAL` and `سحب نقدي ATM` are not offered as a transfer to Cash wallet; `INSTAPAY TRF TO VODAFONE CASH` not to Vodafone Cash. | `files/s2f.csv` | 7AC |
| F13 | low | No first category for a new name, even an obvious supermarket. | `files/s2f.csv` | 7AC |
| F14 | low | A one-row group repeats its name, amount and state on the row below (A16: a line that repeats its label). | `review-bank-descriptions.png` | 7AD |
| F15 | low | "Transfer across currencies" folds under every row of an EGP-only statement. | `review-bank-descriptions.png` | 7AD |
| F16 | medium | The look-alike note says "Same date and amount" for a salary dated the 4th against an entry on the 1st, and never names the entry. | `files/s2f.csv` | 7AD |
| F17 | low | Rows confidently linked to a typed entry still read "Possible duplicate"; the good outcome sounds like a warning. | `files/s1_cib_full.csv` | 7AD |
| F18 | medium | The final summary counts "2 duplicates" without saying which, or their total, or a way back to them. | `files/s1_cib_full.csv` | 7AD |
| F19 | medium | The statement's Balance column is ignored: the strongest check of an import (end balance equals Lightning's) and the opening balance of a new account are lost. | `files/s1_cib_full.csv` | 7AE |
| F20 | medium | Existing holdings are added one form at a time; a new symbol needs another page first. Ten holdings ≈ twenty forms. | `/investments/new?kind=holding` | 5N |
| F21 | medium | On a brokerage account, `Buy 100 COMI @ 85.20` and `Dividend ABUK` are treated as spending and income needing a category. | `files/thndr.csv` | 5N |

What worked well: the 44 rows already typed by hand were each matched to their entry and linked by default (no double
counting); re-importing a posted file is caught; the AI prompt for a rejected file is specific and useful.

## Fixed in this branch (F2, F2b)

- `lightning/bank_import_proposals.py`: rows of one file that share date and amount are noted (`_twin_in_file`), not held
  back; only the ledger, another waiting review, a reference or an earlier void makes a look-alike. When you typed one of
  two same-day payments, the first row links to it and the second defaults to "Post as new".
- `bank_import_preview.html`: the bulk bar gains **Post as new**; the filter row gains **Select all shown**. Deciding 40
  look-alikes is now: Possible duplicates → Select all shown → Post as new (or Skip).
- Tests: `test_two_same_day_payments_in_one_file_both_post_by_default`,
  `test_review_offers_post_as_new_for_ticked_rows_and_select_all_shown` (`tests/test_bank_imports.py`) and the updated
  `test_two_equal_purchases_on_one_day_stay_distinct` (`tests/test_bank_import_matching.py`).

## Suggested order

7Z first (wrong money). Then 7AA and 7AC together: they decide whether a real Egyptian statement can be imported without
hand work. 7AE gives people a reason to trust the result. 7AD, 7AB and 5N after.

## Validation and limits

HTTP and Chromium against the demo profile; dummy files only. Not checked: PDF statements (CIB text PDFs have their own
reader), the phone layout of the review, the SMS flow, the Arabic interface of the review (3AV covers part of it), and the
Windows desktop app. The owner's own file was not seen; its pain points were inferred from their description.

## Dated follow-ups

**2026-11-05, same day: 7Z, 7AA and 7AC built** (commit after `75d63ae` on `claude/post-update-testing-ux-7quo2s`).
Replaying the scenarios: every bank file now reaches the map step with its columns matched (Arabic in UTF-8 and cp1256,
title lines and totals left out, Dr/Cr chosen as the debit/credit marker), and the 46-row CIB statement shows 15 named
groups instead of 46 "No counterparty", with categories from history.
- F1 (7Z): a "Debit/credit marker" column in the map step, suggested from the values; tests
  `test_debit_credit_marker_column_sets_the_sign`, `test_an_unknown_marker_is_a_row_to_fix`. Instead of a note per row
  (refunds put spending categories on money in), the review warns when **every** row of a file is money in:
  `test_map_step_offers_the_marker_and_review_warns_when_every_row_is_money_in`.
- F3-F6 (7AA): `test_arabic_statement_reads_in_every_windows_encoding_and_maps_itself`,
  `test_title_lines_above_the_header_and_total_rows_below_are_left_out`, `test_excel_statement_with_title_rows_reads_from_its_header`.
  The count of left-out summary lines is not shown; a row with a date is never left out
  (`test_a_row_with_a_date_is_never_dropped_as_a_summary`).
- F10-F13 (7AC): `lightning/bank_import_names.py`; tests `test_bank_wording_is_taken_off_the_payee`,
  `test_description_only_statement_suggests_payees_transfers_and_categories`, `test_a_saved_name_inside_a_longer_payee_is_offered_first`.
  A saved name found inside the text is a suggestion to confirm, never merged on its own; a keyword category is marked
  "guessed" and the row shows Needs you.
