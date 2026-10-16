---
title: Offline funding commands need an explicit calendar-context check
category: technical-bug
area: journal
status: reported
created: 2026-10-16
reporter: Codex
skills: number-audit
app_version: 1.1.0b1
commit: 2c636d6
repo: app
---

## Report

Severity: high if reproduced (allocation may target a later month).
Code review finding; a cross-month execution has not yet been reproduced.
The experimental journal translates a funding preview fingerprint to financial-state preconditions, then recomputes the token at home (`lightning/sync/journal/commands.py:374`). Funding's default preview selects today's month (`lightning/planning/funding.py:23`), and apply calls that default again (`lightning/planning/funding.py:99`). Calendar passage alone need not change the financial-state fingerprint.

Before enabling this command in native production, test a proposal created before midnight at month end and delivered after midnight with otherwise unchanged financial rows. It must preserve the explicitly chosen period or refuse for a fresh review, rather than silently allocating to the home device's new month. Audit other commands with implicit dates alongside this case. A fix needs a versioned period/day contract and home-side validation; overriding the home clock would bypass current-date validation.
