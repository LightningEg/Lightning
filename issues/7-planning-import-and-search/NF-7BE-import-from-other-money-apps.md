---
title: Bring your history from another money app - Masareef, Money Manager, Wallet and spreadsheets - in one review
type: feature
pillar: capture
size: M
model: sonnet
status: new
created: 2026-11-28
by: Claude
---

## Report
[r41](r41-the-next-big-thing/report.md) phase 2; feedback 2026-11-05 FB1 (a 377-row CSV from another tracker was hard
to import) and 2026-11-08 FB1-FB3 (multi-sheet Excel, encodings, spreadsheet dates). People arrive with years of data.

## Fix
Recognise the export layouts of the most used apps (column names, date and amount formats, category groups, split
rows) and map them to the existing statement review: one decision per new name, categories offered from the source's
own groups, duplicates flagged. Done when: sanitized sample exports per app in `tests/fixtures/` import through the
review with every row accounted for, and the 377-row layout from the feedback passes.
