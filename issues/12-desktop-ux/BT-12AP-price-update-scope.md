---
title: Price updates must respect all holdings and physical-item valuation
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

[r37](r37-investment-workflow/report.md) F4, F5. The Prices page builds a dictionary keyed only by asset ID, losing all but one account position. With 91 units at one broker and 50 at another, a total value of 1,500 becomes price 30 and combined value 4,230. Separately, a named gold item valued at 50,000 accepts Total value 60,000 and redirects successfully, but remains worth 50,000: the route writes ordinary asset prices while the physical-item valuer reads its own manual-value table/reference.

Evidence: [reproduction and results](r37-investment-workflow/evidence/reproduce.txt).
Run `python issues/12-desktop-ux/r37-investment-workflow/evidence/reproduce.py` from the repository root.

## Investigation

Reviewed at `603d7fe34c20e66121757b2419d68d55a69ca0c0`. Cause: `lightning/ui/routes/investments.py:725`, `lightning/ui/routes/investments.py:943`, `lightning/reporting/valuation.py:51`.
These are dummy-data reproductions; no real holdings were changed.

## Fix

Define the total-value scope explicitly and aggregate the same quantities shown to the user (including clear custody treatment); route named-item overrides to the physical valuation service or link to its proper form. Show a verified resulting value after save. Test two brokers, differing quantities, custody, one-piece and multi-piece gold, unit price vs total value, and invalid values.

Audit only: implementation has not started. PC is the owner's priority (2026-11-14).
