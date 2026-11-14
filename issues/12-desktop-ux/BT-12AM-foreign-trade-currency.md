---
title: Foreign trade forms must name the currency they record
type: bug
look: technical
severity: high
pillar: own
size: M
model: opus
status: new
created: 2026-11-14
by: Codex
skills: bug-hunt, number-audit
app_version: 2.2.1
commit: 603d7fe3
repo: app
---

## Report

[r37](r37-investment-workflow/report.md) F1. The PC and phone general buy forms print Amount (EGP), Price per unit (EGP), and Fees (EGP) for a USD asset/account. Posting 10 units and amount 100 consumes USD 100 and records EGP 5,000 at USD/EGP 50. A user following the label would expect EGP 100. The broker-register entry is a separate path; do not fix only that path.

Evidence: [reproduction and results](r37-investment-workflow/evidence/reproduce.txt).
Run `python issues/12-desktop-ux/r37-investment-workflow/evidence/reproduce.py` from the repository root.

## Investigation

Reviewed at `603d7fe34c20e66121757b2419d68d55a69ca0c0`. Cause: `lightning/ui/templates/investments/form.html:43`, `lightning/ui/templates/phone/investments/form.html:31`, `lightning/ui/routes/investments.py:507`.
These are dummy-data reproductions; no real holdings were changed.

## Fix

Make the selected asset/account determine the monetary input currency and show a separate conversion preview when needed. Apply the same rule to buy, sell, dividend, return of capital, opening holding, fees and edit. Test a real PC selection change, prefilled holding action and backend posting; the label and cash debit must agree.

Audit only: implementation has not started. PC is the owner's priority (2026-11-14).
