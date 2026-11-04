---
title: Read PDF and Excel statements through the CSV review
type: feature
pillar: capture
size: L
status: building
created: 2026-10-19
by: Claude
---

## Report
Size caps, no macros, no formulas run. Idea from Say, Quicken and Monarch.

## 7B1 Design: parser choice, size caps, no macros, no formulas run · M
Pick the library and write the limits; the result is a short decision in this item.

## 7B2 Excel statements through the CSV review · L
Map columns once, review every row, like a CSV.

## 7B3 PDF statements through the CSV review · L
One bank layout at a time, from dummy fixtures only.

## 7B4 Tests and a Mohab step · M
Dummy fixtures for each layout; a strict known_gap until it works.

## Owner decisions · 2026-11-04

Complete Section 7 without helper agents. Start with CIB and text-based PDFs only. The supplied CIB PDF has no extractable text; the owner explicitly chose to keep OCR outside Lightning. Add a local Copy/Edit AI prompt to convert such PDFs to the existing CSV review, with no automatic upload. Real statements stay out of the repository; fixtures contain fictional data.

## Reader decision

Use openpyxl 3.1.5 for literal .xlsx cells, defusedxml 0.7.1 for safe XML, and pypdf 6.10.0 for aligned CIB text. No macros, formulas or embedded PDF actions execute. Excel/PDF input is capped at 8 MB; workbook XML 32 MB, 2,000 archive members, 10,000 rows and 80 columns; one nonempty sheet. PDF: 20 pages, 200,000 text characters per page, one million total. Refuse formulas, macros, multiple nonempty sheets, encrypted PDFs, unsupported/ambiguous layouts and unreconciled printed balances. Older .xls files should be exported as CSV. Parsed documents go through the existing mapping, duplicate detection, review and confirmation; the original document is not stored or sent to AI.

## Implemented and checked

`statement_files.py`, the existing import upload/review route, and the local AI prompt implement the reader decision above. `tests/test_statement_files.py` checks literal Excel, formulas, macros, multiple sheets, bounds, CIB debit/credit/reference parsing, wrong currency, unreadable PDFs, balance mismatches and harmless repeated confirmation. `tests/test_mohab_statements.py` exercises both supported document types through the real screens. Focused reader/import/Arabic/AI checks: 84 passed; Mohab's existing year: 111 passed; the two new document journeys: 2 passed. Full-suite/PR validation and the owner-held packaged check remain before closure.
