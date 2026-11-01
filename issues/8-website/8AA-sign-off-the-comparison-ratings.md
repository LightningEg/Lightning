---
title: Sign off the Low, Medium and High ratings on the comparison pages
type: owner
pillar: reach
status: ready
created: 2026-11-01
by: Claude Sonnet 5.5
skills: none
repo: website
post: no
---

## Report

The three comparison pages (a spreadsheet, a traditional expense tracker, a cloud budgeting app; English and Arabic) are built and
merged from one scorecard, `comparisons.json` in the website repository. The ratings are **proposed**: each cites a row of
`ai/COMPETITION.md` or a test, but you decide what the site claims. Lightning is rated Medium on quick logging and on ease of
starting, and High on data ownership, wealth depth, Egypt fit and traceable numbers.

## Fix

Read the scorecard (the pages show it as a table), change any rating you disagree with, and say so here. Then a session edits
`comparisons.json`, runs `python tools/comparisons.py build`, and the pages follow. Until you sign off, the pages stay but are not
linked from the menu or the home page.
