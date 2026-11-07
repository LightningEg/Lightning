---
title: A fill-in starter workbook with examples: accounts, categories and entries by name, codes handed back
type: feature
pillar: capture
size: L
status: ready
created: 2026-11-07
by: Claude
---

## Report
Today's onboarding workbook (Move your data › `/exports/import/template`) is an export of an empty profile: database
ids, lower-case mapping columns, no examples, and it imports only into a new empty profile
(`lightning/workflows/workbook_import.py`). A person cannot fill it by hand. Wanted (owner, 2026-11-07): a shell people
fill in themselves, with examples, writing **names**; Lightning gives the **codes** (account code, category code, entry
reference) back afterwards.

## Owner decisions (2026-11-07)
1. **One Excel workbook** (`.xlsx`), read with the existing safe reader (no macros, no formulas run, no links).
2. **Into the open profile, review first.** It adds; it never overwrites or deletes; the preview lists what will be
   created, what matched something that exists, and what could not be placed. Entries are duplicate-checked.
3. **A result file with a Codes sheet:** after import the person downloads the same workbook with every new account,
   category and entry's code filled in, so a later batch can refer to them by code instead of by name.

## Rules
- Nothing financial is computed in the workbook or in JavaScript: amounts are read as plain decimals (at most six
  places), signs and currencies kept; posting goes through `TransactionService`.
- Names the person types stay as typed; built-in categories and the seeded system records are matched, never duplicated.
- No invented opening balances, FX rates or category guesses: a row that cannot be placed is listed, never dropped
  silently (same promise as `SETUP_PROMPT`).

## 7AC1 The template: Read me, Accounts, Categories, Entries, with examples · M
`lightning/workflows/starter_workbook.py` builds the `.xlsx`: a *Read me* sheet in plain words (English and Arabic
headers), then *Accounts* (name, type, currency, opening balance, code left empty), *Categories* (name, group, kind,
code left empty) and *Entries* (date, account, category, counterparty, amount, currency, note, reference left empty),
each with two or three example rows marked "Example: overwrite or delete" and drop-downs for type, kind and currency.
Done when: a test opens the file with the safe reader and finds every sheet, heading, example row and drop-down list.

## 7AC2 Read it and preview it against the open profile · L
Match each name to what exists (accounts, categories, counterparties) or mark it new; read dates, signs and currencies
the way the CSV import does (7AA); list rows that cannot be placed with the reason. Confirming creates the new accounts
and categories, then posts the entries in one settled write. Done when: tests cover a clean file, names that match,
new names, an unknown account, a bad date or amount, a repeated upload (nothing posted twice), and Mohab's sample
profile unchanged by an empty template.

## 7AC3 The result file with a Codes sheet · M
After confirming, offer the workbook back with the Codes column filled for every account, category and entry created
or matched, and a *Codes* sheet listing them. Done when: re-uploading that file adds nothing twice and a row may name an
account by its code.

## 7AC4 The page, the guide and the words · M
Move your data gains "Download the starter workbook" beside the existing onboarding workbook and says which is for
what; Arabic through the normal i18n (arabic-check skill); a Mohab step that fills the starter, imports it and finds
the codes. ARCHITECTURE and the Glossary ("starter workbook", "code") are updated.
