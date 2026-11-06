---
title: Read a whole import file before its rows, so dates, signs, currencies and layouts are never guessed per row
type: tech
pillar: capture
size: L
status: new
created: 2026-11-05
by: Claude Opus 5.5
skills: bug-hunt
github: 351
---

## Report

The [CSV import stress test](../../reports/2026-11-05-csv-import-stress/report.md) ran 34 dummy files. Four kinds
post wrong money silently (month-first dates, direction columns, currency and account columns), large files make a
25 MB page, and bank descriptions never become counterparties. The report's *Proposed architecture* is the design;
these steps follow it. Built nothing yet.

## 7AA1 File-level date order · M
Profile every date cell once; month-first, ISO with time and month names read correctly; ambiguous files ask once. Done when: report A12, A13, A14 and B1 dates are right.

**Built 2026-11-06:** `lightning/import_profile.py` (month-first, times, month names, ISO timestamps; A12-A14 re-run clean). Open: ask once when a file is ambiguous (all parts 12 or less; reads day-first, as before); B1 waits for 7AA2.

## 7AA2 Amount plus direction column · M
A third amount model: an amount and a column whose values say in or out (DR/CR, Debit/Credit, Income/Expense); drop "type" as a Category alias. Done when: A4 and B1 post the right sign.

**Built 2026-11-06:** Direction column (`direction_sign` in `bank_import_rows.py`), suggested from DR/CR-style headers or a bare Type column whose values all say in/out; A4 posts the right signs. B1 still needs its Amount found (header "EGP") and its Subcategory: left for 7AA3/7AA7.

## 7AA3 Currency per row · M
A Currency column is matched; a row in another currency waits for the account's amount (or a reference-amount column) and never posts its own figure. Done when: B2's USD row cannot post as EGP.

**Built 2026-11-06:** Currency column matched (`currency_code`, LE/Arabic names read as EGP); a row in another currency is an error row and never posts. Open: using a reference-amount column to fill the account amount, and IT-7Z2 (account column).

## 7AA4 Merchant name from the description · M
A cleaned merchant name fills Counterparty and the raw text stays in Notes, learned through counterparty aliases. Done when: A2 and C3 group by merchant and reuse last month's category.

## 7AA5 Read any layout · M
Encoding detection (UTF-16, cp1256), header row after a preamble, Arabic header names, balance-only statements. Done when: A6, A7, A10, A11 and A17 reach the review.

## 7AA6 Non-transactions as skips · S
Totals footers, zero amounts and future holds open as skipped rows with a reason. Done when: A8, A15 and A16 have no error rows.

## 7AA7 Category paths and subcategories · S
Split `:`, `>`, `/` paths and a Subcategory column into group and name; resolve split lines as one split. Done when: B3 and B6 resolve.

## 7AA8 Review at any size · L
Page the review by name group, render rows on demand, run batch-wide actions on the server, post in chunks. Done when: 5,000 rows review under 1 s with a page under 1 MB.

## 7AA9 Reconcile against the statement's balance · M
With a Balance column, compare the account after each statement day and show gaps or doubles before leaving. Done when: a file with one row removed is caught.

Order: 7AA1, 7AA2, 7AA3 (with IT-7Z2), then 7AA8, 7AA4, the rest. The profile (report stage 2) is built in 7AA1 and extended by each step.
