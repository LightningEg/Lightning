---
title: The brand audit's page-jump check fails on /welcome only under a parallel full run
type: bug
look: technical
severity: low
pillar: build
size: S
status: ready
github: 228
created: 2026-10-29
by: Claude Opus 5.5
app_version: 1.5.1
commit: 7b96469
repo: app
---

## Report
`tests/test_brand_audit.py::test_page_jump_stays_outside_the_figures` failed three times in
`pytest -n auto --dist loadfile` on 2026-10-29 with `{'/welcome': ['Page control overlaps the content column']}`, on
`main` and on branches that touch no PC page. Run alone, it passes every time. The check (line 71 onwards) reads
`#page-jump`'s opacity and box once; under load it likely measures before the page's styles or transition settle.

## Fix
Wait for the jump control's resting state (or `document.fonts.ready` and one animation frame) before measuring, then
run the full suite in parallel three times without a failure.
