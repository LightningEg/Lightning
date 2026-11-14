---
title: General price entry must not override certificate principal
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

[r37](r37-investment-workflow/report.md) F6. The certificate row hides New price per unit as Set at purchase, but still offers Total value. Entering 2,000 for a 1,000-principal certificate is accepted; the portfolio becomes 2,000 and invents a 1,000 gain. Server-side generic price writes also accept it. This bypasses the contract and is separate from the planned interest-accrual model.

Evidence: [reproduction and results](r37-investment-workflow/evidence/reproduce.txt).
Run `python issues/12-desktop-ux/r37-investment-workflow/evidence/reproduce.py` from the repository root.

## Investigation

Reviewed at `603d7fe34c20e66121757b2419d68d55a69ca0c0`. Cause: `lightning/ui/templates/investments/prices.html:71`, `lightning/ui/routes/investments.py:943`.
These are dummy-data reproductions; no real holdings were changed.

## Fix

Make contractual certificates read-only on general price forms and guard manual/CSV price paths on the server. Adjust terms or record actual redemption via the certificate workflow. Any accrued-interest estimate belongs to IV-12J3. Test that ordinary price inputs cannot change certificate value or invent a return.

Audit only: implementation has not started. PC is the owner's priority (2026-11-14).
