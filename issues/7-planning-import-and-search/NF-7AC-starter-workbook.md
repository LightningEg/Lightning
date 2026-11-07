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

## Built so far
7AC1-7AC3: the template, its preview and import, and the result file with codes (`lightning/workflows/starter_workbook.py`, `starter_import.py`, `starter_result.py`, `tests/test_starter_workbook.py`, `tests/test_starter_import.py`, `tests/test_starter_result.py`; see ARCHITECTURE › Starter workbook). Not reachable from a page yet (7AC4). Journal profiles are refused until the journal commands can post it. Rows marked `Example` in column A must be ignored by the reader (7AC2); the Lists sheet is hidden.

## Rules
- Nothing financial is computed in the workbook or in JavaScript: amounts are read as plain decimals (at most six
  places), signs and currencies kept; posting goes through `TransactionService`.
- Names the person types stay as typed; built-in categories and the seeded system records are matched, never duplicated.
- No invented opening balances, FX rates or category guesses: a row that cannot be placed is listed, never dropped
  silently (same promise as `SETUP_PROMPT`).

## 7AC4 The page, the guide and the words · M
Move your data gains "Download the starter workbook" beside the existing onboarding workbook and says which is for
what; Arabic through the normal i18n (arabic-check skill); a Mohab step that fills the starter, imports it and finds
the codes. ARCHITECTURE and the Glossary ("starter workbook", "code") are updated.
