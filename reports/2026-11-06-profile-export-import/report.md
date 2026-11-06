# Profile export and import: why the file is hard to read and will not import, and how to rebuild it

Date: 2026-11-06 · Author/reviewer: Claude (owner-requested audit; no code changed)
Repository: app · Reviewed commit: 4af457b27dfe5ac15d05e518c624f928f1eb22fc
Historical ID: profile-export-import

## Scope and method

**Question (owner).** "Export your data" makes a file that is hard to read (account IDs instead of names, more than
20 tabs), and importing that same file into another profile does not work. Audit it and architect the structure:
one file exported from a profile must import into a different profile without issues. Do not fix.

**Included.** `lightning/workflows/data_export.py` (Settings › Export your data, Reports › Export all data),
`lightning/workflows/workbook_import.py` and `lightning/ui/routes/exports.py` (Settings › Import your data), the
welcome page's currency step, and `tests/test_workbook_onboarding.py`. **Excluded.** Bank-statement CSV import
(audited in [the CSV stress report](../2026-11-05-csv-import-stress/report.md)), encrypted backups and restore
(IT-2A), phone hand-off (4B).

**Method.** Source reading, then real round trips on dummy data: the demo household, Mohab's 2026 sample and two
sample stories, exported through the route and imported through the route's preview and confirm. Then the same
file under five real-life conditions: a new profile after its welcome step, the file saved by a spreadsheet app,
a file from an older Lightning, and the CSV choice. One script reproduces every finding:
[`evidence/roundtrip.py`](evidence/roundtrip.py), output in [`evidence/roundtrip-output.txt`](evidence/roundtrip-output.txt).

## Verdict

The import works only in a laboratory: a database nobody has touched, the exact bytes Lightning wrote, the same
Lightning version. Every ordinary path a person takes breaks it. The cause is one design choice: **the file is
the database, table by table** (58 tables plus a Read me, each column a schema column, each reference a row
number). That makes it unreadable for people and brittle for import, because any change on either side (a
setting chosen on the welcome page, an empty cell after Excel saves, a new table in the next release) is a
mismatch. The fix is not more validation; it is a **profile file with its own stable format** that Lightning
translates to and from the database.

## Findings

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | high | **Fifty-nine sheets, one per table.** Mohab's export has 59 sheets; 20 are empty, and several are internal (`audit_log`, `currency_suggestions` with 181 seeded rows, `bank_import_rows` staging, `reevaluation_*` checkpoints, `profile_identity`). Sheet names are table names (`reevaluation_suppressed_account`, cut at 31 characters). Expected: about ten sheets a person recognises, named as the app names them. | output F1; `data_export.py` `TABLES` | BT-2AJ1 |
| F2 | high | **IDs where names belong, and every fact twice.** Readable columns are bolted onto the schema columns, so `ledger_entries` has 29 columns: `Date` and `date`, `Total in currency` and `amount`, `FX rate` and `fx_rate`, `Transaction ID` and `transaction_id`. Eleven `*_id` columns have no name at all (for example `reserve_allocation_history.reserve_id`, `bank_import_rows.batch_id`). Types and states are codes (`OPN`, `POSTED`, `SYSTEM`); timestamps are UTC machine strings. Expected: one column per fact, a name in every reference, a stable number to track each record by. | output F1; `export_tables` | BT-2AJ1 |
| F3 | high | **A real new profile is "not empty".** The welcome page asks for the profile currency first. Choosing EGP plus one more currency, or a base other than EGP, registers currencies; `_has_custom_setup` compares every table with a fresh seed and refuses: "Import into a new, empty profile. Your existing setup would otherwise be overwritten." Only a profile whose owner chose EGP alone, or skipped the step, can import. Expected: the welcome choices are not "records"; empty means no accounts, transactions or plans. | output F3; `workbook_import.py` `_unused` | BT-2AJ3 |
| F4 | high | **Opening and saving the file in a spreadsheet app breaks it.** An empty text value (for example an account's blank Notes) is written as an empty string; a spreadsheet app saves it as an empty cell or an `inlineStr` cell with no text. The reader crashes on the second (`'NoneType' object has no attribute 'itertext'`, shown as "Choose a valid Excel .xlsx workbook") and the loader refuses the first ("NOT NULL constraint failed: accounts.notes"). With only that one rule changed (blank text = empty text), the LibreOffice-saved file imports. Expected: a file a person opened, looked at and saved still imports. | output F4 | BT-2AJ2 |
| F5 | high | **A file from an older Lightning never imports.** Import demands every sheet and refuses any column it does not know; there is no format version. `other_asset_details` arrived on 2026-11-05 (#323), so a file exported the day before fails: "This is not a complete workbook. Missing sheets: other_asset_details." Each of the 76 migrations is such a break. Expected: a versioned format; older files upgrade, a missing optional sheet is empty, an unknown column is reported and ignored. | output F5; `prepare_import` | BT-2AJ1, BT-2AJ2 |
| F6 | medium | **The CSV choice cannot be imported.** Export offers "CSV files in a ZIP"; import accepts only `.xlsx` and says "Choose a valid Excel .xlsx workbook", with no hint that the ZIP is for reading only. The Read me inside the ZIP says so; the export page does not. Expected: the file to move a profile is one choice, named as such. | output F6; `exports/all.html` | BT-2AJ4 |
| F7 | medium | **Editing a name is refused.** `_validate_context` checks that every readable column equals the name the ID points to; correcting "CIB payrol" in the Account column fails with "differs from its mapping column". The file is readable, but only the ID columns count. Expected: one column per fact; a name is the reference. | `test_invalid_workbook_is_atomic…` | BT-2AJ1 |
| F8 | medium | **Import writes tables, not records.** `_load` deletes and re-inserts every table with the file's row numbers. It works only when the target's schema equals the source's, it copies derived data (month-end checkpoints, carry-overs, audit log) as if it were fact, and it has no branch for an *Edit from your devices* profile, where writes go through the journal (not run; source shows no journal check). Expected: a loader that creates records through the domain layer, gives them new local IDs and rebuilds derived data. | `_load` | BT-2AJ3 |
| F9 | low | **The review page carries the whole file back.** Preview puts the workbook into the page as base64 (229 KB for Mohab's year; up to 21 MB for a 16 MB file) and the confirm posts it again. Expected: hold the upload server-side for the token's 15 minutes. | output of the route run; `exports.py` | BT-2AJ4 |
| F10 | low | **The tests cannot see any of this.** `test_workbook_onboarding.py` round-trips one account and two transactions into an untouched database, with the same bytes and version. Expected: Mohab's year and each story through the route, after the welcome step, after a spreadsheet re-save, and from the previous format. | test file | BT-2AJ5 |

What worked: on an untouched database every sample (demo, Mohab's 2026, Amr, Abdelrahman) round-trips, the preview
never changes the live profile, formulas, macros and external links are refused, and imported figures match.

## Proposed architecture

### 1. One file, its own format

A **Lightning profile file** (`.xlsx`, "Lightning profile – <name> – <date>.xlsx") is a format of its own, not a
dump of the database. It is versioned (`Format 1`), readable as the app reads, and it is the only file that moves
a profile. Export translates database → format; import translates format → records. The schema can change every
week; the format changes rarely and each change ships an upgrader from the previous version.

### 2. Ten sheets, named as the app names them

| Sheet | One row per | Carries (from today's tables) |
| --- | --- | --- |
| Read me | — | Format version, app version, export date, profile currency, what each sheet holds, and the **check figures**: records per sheet, balance per account, net worth on the export date |
| Transactions | ledger line | `transactions` + `ledger_entries` (+ links: reserve, reimbursement, CD receipt) as columns: No., Date, Type, Account, Category group, Category, Counterparty, Amount, Currency, Rate, Amount in EGP, Holding, Units, Price, Owner, Note, Status, Cleared |
| Accounts | account | `accounts`, `institutions`, `reconciled_through`, cost method, opening and closing dates |
| Categories | category | `categories` as Group and Name (two levels, plus a third where it exists), kind, archived |
| People and places | counterparty | `counterparties` + `counterparty_aliases` (aliases in one cell) |
| Holdings | asset | `financial_assets`, custom `asset_classes`, physical items, other-asset details, CD certificates and terms, investment targets |
| Prices and rates | dated price | `price_history`, `fx_rates`, item and other-asset valuations, manual month-end prices |
| Plans | plan | `planned_items`, `planned_payments`, loans, installments, gameya terms, money from others |
| Budgets and reserves | budget or reserve | `budgets`, carry-over resets, `cash_reserves`, allocation history, `zakat_settings` |
| Settings | setting | the allowed settings, rules (one row each, conditions and actions in readable cells), saved views |

**Not carried, rebuilt on import:** `currency_suggestions` and seeded asset classes (seed data), `registered_currencies`
(from what the file uses), `budget_carryover` (recomputed), `reevaluation_*` (recomputed from Prices and rates; the
step proves by equal figures whether `VAL` lines travel as transactions or are regenerated).
**Not carried, said in Read me:** `audit_log`, `profile_identity`, unfinished bank-statement reviews
(`bank_import_*`, owner decision below).

### 3. Names to read, numbers to track, no row IDs

- Every record has a **No.** column with its existing stable key: `transactions.ref`, `accounts.code`,
  `categories.code`, `financial_assets.code`, and a sheet-prefixed number for the rest. These are already unique in
  the schema and never depend on database row numbers.
- Every reference is the **name** (Account "CIB Payroll"), never an ID. Names are unique within a sheet of the file:
  where two records share one, the export adds the No. ("Cash · A-0007") and the import accepts either form.
- On import, names resolve in memory to new local IDs; nothing in the file is a target row number. A file can go
  into any profile, any schema version, an encrypted or a synchronized one.

### 4. Import pipeline

1. **Read, tolerant of spreadsheet apps.** Blank text is empty text; a number may be a number or text; a date may be
   text, a date cell or an Excel serial; Yes/No, TRUE/FALSE and 1/0 are booleans; spaces are trimmed; column order is
   free; inline strings without text are empty. Still refused: formulas, macros, external links, the size limits.
2. **Recognise and upgrade.** Read me's format version picks the reader; older formats upgrade step by step; a newer
   one is refused with "Update Lightning to open this file". A missing optional sheet is empty; an unknown column or
   sheet is listed in the review and ignored.
3. **Resolve.** Names to records, in memory. Unknown or ambiguous names become review questions, not a dead end.
4. **Check in a scratch copy** (as today): postings balance, no holding below zero, no future dates, every reference found.
5. **Review.** Records per sheet and the check figures side by side: balance per account and net worth from the
   file vs what the import will produce. They must be equal to confirm.
6. **Write through the domain layer** in one transaction (on a synchronized profile, as journal commands), then
   rebuild derived data, then re-run the check figures on the live profile.

### 5. Which profile can receive a file

"Empty" means **no user records**: no non-system account, transaction, plan, budget, reserve, rule or counterparty.
The welcome page's choices (currencies, language, setup flags) do not count; the file's currencies are added to them.
If the profile currency differs and the profile is empty, the review shows "Profile currency becomes EGP" and the
import sets it. Merging into a profile that already has records stays out of scope.

### 6. The export page

One clear choice: **Profile file (Excel)** – to read and to move into another profile. CSV stays, labelled
**For reading only (CSV in a ZIP)**, with the same sheets as files. The import page names the profile file and says
the CSV cannot be imported.

### 7. Proof

The acceptance test exports every sample (Mohab's year and each story), imports it into a profile that went through
the welcome step, and compares the check figures and every screen's numbers; the same after a spreadsheet re-save,
and from the previous format's fixture. Mohab's test gains one step: he moves his year into a new profile.

## Owner decisions

1. **One file or two.** (a) One profile file, readable and importable, as above (recommended: one thing to explain,
   and it is what was asked); (b) a readable export plus a separate encrypted `.lightning` profile copy for moving
   (exact copy, nothing to translate, but a second file to explain and not readable).
2. **Unfinished statement reviews.** Carry them in an eleventh sheet, or leave them behind and say so in Read me
   (recommended: they are a work queue, not records; finish or discard before moving).

## Validation and limits

- Run: `python reports/2026-11-06-profile-export-import/evidence/roundtrip.py` (output in `evidence/`). Plaintext
  test databases only; the encrypted round trip ran through the workflow, not the route, because the test client
  runs on another thread than the encrypted connection's owner.
- The spreadsheet re-save used openpyxl and LibreOffice 7 on Linux. **Microsoft Excel was not run**; it also stores
  an empty text value as an empty cell, so F4 is expected there, but it is unverified.
- The owner's own file was not available; F3 to F6 are the paths that match "I exported it and the import did not
  work". The owner can tell which by the message the import page showed.
- Synchronized (*Edit from your devices*) profiles were not tried; F8's journal gap is from source reading.
- Sample story "menna" did not load in this environment (a counterparty-similarity refusal in `load_story`); it is
  unrelated to export and was not investigated.

## Dated follow-ups

2026-11-06, owner decisions: (1) one profile file, readable and importable; (2) unfinished statement reviews are left behind and counted in Read me. Recorded in BT-2AJ.
