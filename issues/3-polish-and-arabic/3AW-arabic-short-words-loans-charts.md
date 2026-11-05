---
title: Four short words stay English in Arabic on loans, charts and investments
type: bug
look: visual
severity: low
pillar: feel
size: S
status: ready
created: 2026-11-05
by: Claude Sonnet 5.5
app_version: 1.5.4
repo: app
---

## Report
`translate(..., 'ar')` returns these unchanged: "Paid off" (`planning/early_payment.html:11`), "paid" (`planning/loans.html:7`), "a year" (`investments/index.html:34`), "since the last point" (`partials/charts.html:19`). Not yet confirmed on a rendered page: check in the demo first, and if one is already handled elsewhere, say so on the GitHub issue.

## Done when
Each word shows in Egyptian Arabic on its page, and the Arabic no-English test covers `/plan/loans` and `/investments`.

Where to look: the four templates above and `lightning/ui/i18n.py`.
Read first: `guideline/website-ar.html` B04.
