---
title: A guideline rule for an Arabic page that links to an English page - the label says so and it opens in a new tab
type: polish
pillar: reach
size: S
model: opus
status: parked
created: 2026-11-11
by: Claude
skills: none
repo: website
post: no
---

## Report

Owner decision 2026-11-11 (OW-8D): make the For Geeks footer's convention a guideline rule. Today the Arabic footer's For Geeks link is labelled «(بالإنجليزي)» and opens a new tab, but no rule says so. The website's stats-in-CI idea was not chosen: a job that clones the app would turn unrelated site PRs red after any app merge, so `python tools/geeks_stats.py ../Lightning --check` stays a manual check.

## Fix

Add the rule as B09 in `guideline/website.html` (and its Arabic counterpart if the guideline keeps one), copy it to the website repository (`cmp` must pass), then make every Arabic page that links to an English-only page follow it.

## Done when

The rule is in both repositories' guidelines, every such link follows it, and `tests/test_docs_structure.py` passes with the sibling repository present.
