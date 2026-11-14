---
title: Amount-only sales must add fees before deriving units sold
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

[r37](r37-investment-workflow/report.md) F3. In the broker register workflow, leave Units empty, set Sell, price per unit 10, net amount received 100, fees 10 included. It sells 9 units rather than 11. Cash received is 100 in both cases; remaining units and subsequent gains are wrong. Units are derived using the buy formula (amount minus fee) for a sale.

Evidence: [reproduction and results](r37-investment-workflow/evidence/reproduce.txt).
Run `python issues/12-desktop-ux/r37-investment-workflow/evidence/reproduce.py` from the repository root.

## Investigation

Reviewed at `603d7fe34c20e66121757b2419d68d55a69ca0c0`. Cause: `lightning/workflows/investment_entry.py:128`.
These are dummy-data reproductions; no real holdings were changed.

## Fix

For a sale entered as net proceeds, derive units from (net + fee) / price. Keep buy and fees-extra semantics distinct, and follow asset precision. Test amount-only buy/sell, fees included/extra, explicit units and an oversell near the fee boundary through the register POST.

Audit only: implementation has not started. PC is the owner's priority (2026-11-14).
