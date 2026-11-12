---
title: Moving data in from a workbook still fails and is hard to do
type: bug
look: technical
severity: high
pillar: own
size: M
model: opus
status: ready
created: 2026-11-12
by: Claude Opus 5.5
github: 614
---

# Moving data in from a workbook still fails and is hard to do

The owner filled the onboarding workbook with an AI tool (Settings › Move your data › Import your data) and the running
app answered "This form expired" every time (2026-11-12).

## What was wrong, and is fixed (branch `claude/adoring-ptolemy-i3cogr`)

1. The app guard allowed no file part and 512 KB on `/exports/import` and `/exports/starter`, so every real upload read
   as an expired form; the tests used a client without the guard. Now one file and a bounded workbook body
   (`lightning/runtime/app.py`, `http.py`; `tests/test_profile_app.py`).
2. Text cells written as `t="str"` (Open XML SDK, used by AI tools) were refused as "unsupported cell type".
3. Blank cells in required text columns (`accounts.notes`, an empty setting) failed with a raw SQLite message: Excel
   cannot keep an empty text. They now take the column's default.
4. Every timestamp (`created_at`, `updated_at`, `posted_at`) came in as an Excel serial (`46325.77`), and would have been
   stored as that. Serials in date and `_at` columns become ISO text (`tests/test_workbook_onboarding.py`).

With these the owner's file previews and imports: 1,739 records, 4 accounts.

## What is still hard (this item)

## 7AS1 Errors name the sheet, row and column in plain words · S
"Workbook data violates a required type, unique key or financial constraint: NOT NULL constraint failed: x.y" is the
raw database text. Say which sheet, row and column, and what to put there; list every problem at once, not one per upload.

## 7AS2 The review page speaks the person's words · S
It lists 60 table names (`ledger_entries`, `bank_import_rows`); show what is coming in (accounts, entries, categories,
budgets) with counts, and hide empty internal tables.

## 7AS3 Fewer ways to get the workbook wrong · M
The full workbook needs 63 sheets whose readable and mapping columns must agree, from an AI prompt. Check booleans
(TRUE/FALSE), numbers saved as text and other Excel conversions the way serials are now; keep a sanitized AI-made
workbook as a test fixture.

## 7AS4 Starter or full workbook: one door · S
The starter page and the full import look alike; a full workbook uploaded to the starter page fails with "no Entries
sheet". Detect which one it is and send it to the right review.

**Done when:** an AI-filled workbook made from the template and the setup prompt imports on the first try, or each
problem is listed with its sheet, row and column; Mohab's import step passes.
