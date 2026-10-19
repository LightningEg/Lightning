---
title: App and website guideline copies differ despite matching version labels
type: bug
area: website
status: building
created: 2026-10-16
by: Codex
skills: none
app_version: 1.1.0b1
commit: 73e55ab
repo: both
---

## Report

Low severity. With `Lightning_website` checked out beside the app, run
`python -m pytest tests/test_docs_structure.py::test_the_app_and_website_guidelines_are_the_same_three_files -q`.
It fails on `guideline/app.html`: both copies report version 3.30 but their bytes
differ. Neither the guideline nor this test changed in the edit-journal work.
Expected: all three guideline copies match after newline normalization.

## Investigation

Codex, no skill: this predates the journal branch. `NOW.md` already lists the
website guideline copy sync as unfinished. It remains open because the current
work is the journal; resolve through that existing website-sync task and delete
this report in the fixing commit.

A guideline-only fix is tested and pushed to the website branch
`codex/sync-app-guidelines` (`14b4013`). Publication to that separate repository's
main branch awaits owner approval after automatic approval review rejected it
because the app task does not explicitly authorize website publication.
The local paired-checkout test passes against that review branch.
