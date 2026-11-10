---
title: The Investments Lead's Cost and Unrealized gain do not add up to its Portfolio value - 325,088 and 27,399 under 752,486
type: bug
look: technical
severity: medium
pillar: own
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: number-audit
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r36 F4 ([report](../11-phone-ux/r36-figures-one-owner/report.md), [page text](../11-phone-ux/r36-figures-one-owner/evidence/sample-pages.json), key `pc:/investments`; first seen in r35 F6). Mohab's sample year, 2026-10-21: the Lead says Portfolio value 752,486, and its bar and line say "Cost 325,088 · Unrealized gain +27,399". The holdings table under it says Cost 725,088, Value 752,486.

Cause: `lightning/ui/routes/investments.py` lines 128-129 work the two parts out in the route (`owned_cost = p.cost_basis - custody_cost`, `owned_unrealized = owned_value - owned_cost`) from the investment report, which leaves out holdings that Portfolio value (`Position.portfolio_value`) counts: here a 400,000 flat held as an Other investment. The bar is drawn as if its two segments were the whole figure.

## Fix

One function returns the Lead and its parts together, so they cannot differ: Portfolio value = Cost + Unrealized gain over the same holdings, with what has no cost or market price named as its own part ("Valued by you 400,000") instead of dropped. The route only passes it on. Run skill number-audit invariant 9 before and after.

Test: on Mohab's year the Lead's parts sum to its figure, and the Lead's Cost equals the table's All holdings Cost; a profile with held-for-others units keeps both true.
