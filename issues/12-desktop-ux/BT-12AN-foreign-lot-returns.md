---
title: Each purchase must value foreign units in the same currency as cost
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

[r37](r37-investment-workflow/report.md) F2. Ten USD shares at USD 10, bought at USD/EGP 50, have EGP 5,000 cost and EGP 5,000 current value. purchase_returns reports value 100, gain -4,900 and ROI -98% because it multiplies units by the native price while lot cost is in base currency. The headline is correct; Each purchase is wrong.

Evidence: [reproduction and results](r37-investment-workflow/evidence/reproduce.txt).
Run `python issues/12-desktop-ux/r37-investment-workflow/evidence/reproduce.py` from the repository root.

## Investigation

Reviewed at `603d7fe34c20e66121757b2419d68d55a69ca0c0`. Cause: `lightning/investments/views.py:160`, `lightning/investments/service.py:619`.
These are dummy-data reproductions; no real holdings were changed.

## Fix

Use a dated base-currency unit valuation for lot values/ROI/CAGR, respecting owned quantities and missing FX. Test unchanged price and FX (0%), price-only change, FX-only change, and missing FX. The sum of owned held-lot values must equal the holding value.

Audit only: implementation has not started. PC is the owner's priority (2026-11-14).
