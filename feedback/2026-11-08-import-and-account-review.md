# Import files and account review

Date received: 2026-11-08 · Reviewed: 2026-11-08
Product/build/surface: Lightning desktop and phone; reported build unknown
Source: user feedback in chat, sanitized

Six observations from one respondent, grouped into five implementation items. Themes: file compatibility, efficient review, accurate duplicate detection. No incorrect balance was reported.

| ID | Observation | Expected outcome | Theme | Investigation verdict | Issue / disposition |
| --- | --- | --- | --- | --- | --- |
| FB1 | Multi-sheet Excel cannot select a sheet | Choose a worksheet before import | Files | Defect: reader rejects multiple nonempty sheets | BT-7AD · [file choices](../tests/test_import_file_choices.py) |
| FB2 | Excel and non-UTF-8 CSV uploads fail | Accept supported Excel and common CSV encodings | Files | Defect: worksheet restriction and incomplete encoding coverage | BT-7AD · [file choices](../tests/test_import_file_choices.py) |
| FB3 | Numeric spreadsheet dates such as 46631 fail | Convert Excel serial dates in date columns | Files | Defect: read_date accepts only calendar text | BT-7AE · [serial dates](../tests/test_import_file_choices.py) |
| FB4 | Only 50 entries can be shown and selected | Choose a larger page size | Review | Request: register fixes page_size at 50 | IT-7AF · [page size](../tests/test_register_page_size.py) |
| FB5 | Institution selection does not always set the default type | Thndr selects Brokerage; CIB selects Bank | Accounts | Defect: exact matching and current-type restriction in form | BT-7AG · [browser defaults](../tests/test_import_account_defaults_browser.py) |
| FB6 | Reimport after deletion is still a duplicate | Match active entries and allow explicit new payment | Duplicates | Defect: file history matches inactive rows and voided history forces duplicate state | BT-7AH · [active duplicates](../tests/test_import_file_choices.py) |

## Dated follow-ups

2026-11-08: Code investigation: statement_files.read_excel; bank_import_rows._decode_text; import_profile.read_date; ui.routes.register._reg; accounts/form.html applyInstitution; bank_import_proposals._preview. User explicitly requested implementing all six observations.

2026-11-08: Implemented all six observations. Transactions drop also accepts XLSX/PDF and keeps the worksheet/column continuation; guarded runtime now accepts the UI’s multiple files within its aggregate limit. Account defaults and bulk editing 100 entries pass real Chromium tests at 1366 and 390 widths. [Mohab’s statement journeys](../tests/test_mohab_statements.py) cover worksheet choice and numeric date posting; [guarded drop journey](../tests/test_import_file_choices_browser.py) covers XLSX plus CSV through worksheet and column choices. Serial 46631 displays 2027-09-01 and remains a future-row skip until that date. CSV decoding offers automatic UTF-8/UTF-16/Windows Arabic and explicit Western or Arabic choices; legacy binary XLS is outside this change. Multiple-account bulk drops retain staged reviews; unfinished groups have explicit review actions and a note to reselect other unfinished files after navigation.

2026-11-08 validation: the full suite was run once. Navigation regressions were fixed and their register/browser tests rerun; the upload completion-boundary audit now verifies the synchronous shared helper. An existing quoted multiline CSV failure also reproduced on untouched main; the delimiter reader was corrected and the SMS/import regressions pass. Remaining baseline failures reproduced on untouched main concern investment-link styling, mirrored phone guideline copies, an old browser assertion expecting two displayed transfer rows, and native pairing approval timing; pairing remains with NF-4A. These are not presented as passing checks.
