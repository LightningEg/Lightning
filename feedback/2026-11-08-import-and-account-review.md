# Import files and account review

Date received: 2026-11-08 · Reviewed: 2026-11-08
Product/build/surface: Lightning desktop and phone; reported build unknown
Source: user feedback in chat, sanitized

Six observations from one respondent, grouped into five implementation items. Themes: file compatibility, efficient review, accurate duplicate detection. No incorrect balance was reported.

| ID | Observation | Expected outcome | Theme | Investigation verdict | Issue / disposition |
| --- | --- | --- | --- | --- | --- |
| FB1 | Multi-sheet Excel cannot select a sheet | Choose a worksheet before import | Files | Defect: reader rejects multiple nonempty sheets | BT-7AD |
| FB2 | Excel and non-UTF-8 CSV uploads fail | Accept supported Excel and common CSV encodings | Files | Defect: worksheet restriction and incomplete encoding coverage | BT-7AD |
| FB3 | Numeric spreadsheet dates such as 46631 fail | Convert Excel serial dates in date columns | Files | Defect: read_date accepts only calendar text | BT-7AE |
| FB4 | Only 50 entries can be shown and selected | Choose a larger page size | Review | Request: register fixes page_size at 50 | IT-7AF |
| FB5 | Institution selection does not always set the default type | Thndr selects Brokerage; CIB selects Bank | Accounts | Defect: exact matching and current-type restriction in form | BT-7AG |
| FB6 | Reimport after deletion is still a duplicate | Match active entries and allow explicit new payment | Duplicates | Defect: file history matches inactive rows and voided history forces duplicate state | BT-7AH |

## Dated follow-ups

2026-11-08: Code investigation: statement_files.read_excel; bank_import_rows._decode_text; import_profile.read_date; ui.routes.register._reg; accounts/form.html applyInstitution; bank_import_proposals._preview. User explicitly requested implementing all six observations.
