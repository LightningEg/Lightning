---
title: One workbook or CSV that holds several accounts imports into each
type: feature
pillar: capture
size: L
status: ready
created: 2026-11-05
by: Claude Opus 5.5
---

## Report
People who tracked money in a spreadsheet keep one sheet with an `Account` column, or one sheet per account. Today:
- one sheet with an Account column: "This workbook contains more than one account. Export one account at a time.";
- one sheet per account: "Choose a workbook with one nonempty worksheet";
- a sheet with a running-balance formula: "This workbook contains formulas. Export its displayed values as CSV."
Each is a dead end for the person this import is meant for (moving in). Evidence: [the report](../../reports/2026-11-05-import-scenarios/report.md), F7-F9.

## 7AB1 Split by account · M
When the file has an Account column (or several worksheets), the map step adds one line per distinct value or sheet:
"CIB → CIB Payroll, Cash → Cash wallet, Skip". Names that equal an account's name or institution are pre-picked. Each
account gets its own review batch, opened one after another from a list.

## 7AB2 Pair transfers inside the file · M
A row in account A and the opposite row in account B on the same day for the same amount become one transfer (as the SMS
flow pairs them), not an expense plus an income.

## 7AB3 Formulas read as their saved values · S
Read a formula cell's cached value (openpyxl `data_only=True`) for columns that are not mapped to Date or Amount (a
running balance), and refuse only when a mapped Date or Amount cell is a formula with no cached value. No formula is
ever run.
