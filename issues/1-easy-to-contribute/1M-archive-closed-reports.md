---
title: Archive closed reports and keep their evidence out of the checkout
type: tech
pillar: build
size: M
status: ready
created: 2026-10-31
by: Claude Sonnet 5.5
---
## Report
`reports/` is 15 MB across 19 reports, mostly evidence screenshots (Audit 7 alone is 6 MB). A report whose open follow-ups are all closed is history, not a working document, yet it sits beside the live ones and shows in every search.

## Fix
- `tools/status.py` already reads each report's open follow-up codes from `reports/README.md`. Add `python tools/archive.py` (dry run by default): a report with no open follow-ups, older than 30 days and not a reference (`users-main-questions`), moves to `ai/archive/reports/<folder>/report.md`; its `evidence/` images are dropped (git history keeps them) and the catalogue row moves to an archive table.
- Keep the report text, its verdict and the commit-pinned references issues already use.
- `tools/docs_check.py` and `tests/test_docs_structure.py` learn the archive path; no link in `issues/`, `feedback/` or `ai/` may break.
- Candidates today: Audit 7, dendera-theme, contributor-review, fx-date-boundary, Audit 6 once 1H closes.
