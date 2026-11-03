---
title: Distinguish ambiguous annualized returns from unavailable results
type: tech
pillar: own
size: M
status: new
post: no
created: 2026-11-03
by: Codex
app_version: 1.5.4
commit: 89848dc0e4ce35bb18f72e861c7c620d8052fae4
repo: app
---

## Report

[Code audit F3](../../reports/2026-11-03-code-quality-and-smart-features/report.md). Yearly flows -100, +230, -132.16 have NPV roots 12% and 18%; `xirr` returns None because both roots lie within one scan interval. The adjacent Python evidence verifies both roots. This is a documented solver limitation, not a ledger correctness failure.

## Fix

Specify a policy for non-conventional flows before changing the solver. Introduce an explicit convergence/unavailable/ambiguous result contract and an honest display reason; never select an arbitrary root. Validate known-root, no-root, multi-root, date-spacing and residual-tolerance fixtures. Preserve current ordinary-flow behavior and exact ledger arithmetic.

Not posted: requires financial return semantics to be agreed.
