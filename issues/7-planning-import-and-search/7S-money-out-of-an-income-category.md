---
title: Money out filed under an income category counts as spending, not as less income
type: owner
area: reporting
status: new
created: 2026-10-26
by: Claude
skills: number-audit
app_version: 1.4.2
commit: 705945c
repo: app
---

## Report

Found by [Audit 8](../../reports/2026-10-26-engine-audit/report.md) (A4). After 20,000 in "Gifts received", a −2,000 register row in the same category shows as 2,000 Money out with a "Gifts received" spending row and a 90% savings rate; returning part of a gift reads more naturally as 18,000 Money in and 100%. This follows `flow_of` as documented in Architecture (one rule for Money in and out), and an expense refund has its own route, but an income reversal has none.

## Fix

Owner decision: should a negative line in an income-class category reduce Money in? If yes, change `flow_of` once (every report uses it) and add a Mohab step.
