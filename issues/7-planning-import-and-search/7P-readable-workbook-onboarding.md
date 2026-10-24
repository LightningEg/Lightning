---
title: Readable exports and comprehensive workbook onboarding
type: feature
area: import
status: building
created: 2026-10-24
by: Codex
skills: feedback-review
app_version: 1.4.4
commit: e141406
repo: app
---

## Report
Owner requests plain Arial 11 left-aligned spreadsheet headers and appropriate widths/types; transaction columns in order: Transaction ID, Transaction reference, Account, Date, Counterparty, Currency, Total in currency, FX rate, Total in default currency, Category L1, Category L2. Other columns at tail, no quantity/unit price in cash transaction view. Comprehensive exports need readable names before mapping IDs and navigation through their many sheets. AI export panel should have export, copy, edit buttons plus short instructions; prompt editor in popup. Add comprehensive workbook onboarding import and a prompt explaining how to prepare compatible files.

## Investigation
Confirmed defect: reporting/xlsx.py dark header style lacks mandatory neutral fill. AI transaction layout in workflows/ai_analysis.py exposes quantity/unit price and category path. data_export.py exports raw database columns without related readable names. Existing bank import handles account-specific CSV, not comprehensive onboarding. Owner explicitly requested implementation of all these changes.

## Fix
Design and implement on codex/readable-workbook-onboarding. Validate export OOXML, prompt UI, workbook preview/import safety and financial roundtrip using synthetic records. Never commit uploaded financial data.
