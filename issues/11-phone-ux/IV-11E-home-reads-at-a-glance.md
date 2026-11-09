---
title: Home is a block of sentences - To do rows say who, how much, when and one verb, and the hero says how much a day until payday
type: polish
pillar: plan
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

Report [r29](r29-google-play-readiness/report.md) T2, T3; the owner (2026-11-09): "It has a block of text." To do shows
"NBE 3-year certificate: 2 interest payments to match", "Emergency fund needs you", "Looks recurring", each with "Review"; the hero
line is "May be off: 3 days not recorded." or "On top of your plan until 2026-12-01." Guideline C11.1: `Vodafone 350 · in 3 days  Pay ›`
and "About 1,650 a day until payday on …".

## Fix

Files: `lightning/ui/templates/phone/home.html`, `lightning/ui/phone/screens/home.py`, `lightning/ui/i18n*.py`.
- Each To do row: the thing's name, its amount (or count), when (late / today / in N days), and a verb that says what happens: Pay, Match, Top up, Confirm. "Looks recurring" becomes `Netflix 250 · every month  Make it a bill ›`; "Emergency fund needs you" becomes `Emergency fund 5,404 short  Top up ›`.
- The hero's line is always the daily figure ("About 249 a day until payday on 1 Dec"); "May be off: 3 days not recorded" moves to a To do row (`3 days not recorded  Add ›`).
- Done when: a test renders Home on Mohab's 2026-10-04 and every To do row has a figure and a verb other than Review; the hero line contains "a day"; `python tools/phone_check.py` and `--arabic` print nothing for `/home`.
