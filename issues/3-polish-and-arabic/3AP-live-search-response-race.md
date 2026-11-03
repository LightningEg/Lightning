---
title: An old search body overwrites the latest phone results and URL
type: bug
look: technical
severity: medium
pillar: capture
size: M
status: new
post: no
created: 2026-11-03
by: Codex
app_version: 1.5.4
commit: 89848dc0e4ce35bb18f72e861c7c620d8052fae4
repo: app
---

## Report

[Code audit F2](../../reports/2026-11-03-code-quality-and-smart-features/report.md). `phone-capture.js:150` checks the request serial before awaiting the response body. Run the adjacent `evidence/search-race.cjs`: the field is new but results and URL return to old. It executes the real initializer with controlled fetch responses.

## Fix

Read the body, then check the generation and mounted form immediately before DOM/history updates. Invalidate pending work on input and navigation; abort obsolete requests where useful. Add a real browser regression for delayed bodies, rapid input/clear and navigating away. Keep ordinary non-JavaScript form submission working.

Not posted yet: regression spans asynchronous search and the phone navigation lifecycle.
