---
title: Direct tests for investment_breakdown
type: tech
pillar: build
size: M
model: sonnet
status: ready
created: 2026-11-05
by: Claude Sonnet 5.5
app_version: 1.5.4
repo: app
github: 339
---

## Report
`lightning/planning/investment_figures.py` builds the owned gains, the horizon split and the balance-only holdings behind the Investments table. No test imports `investment_breakdown` or `InvestmentBreakdown` directly (checked by name search in `tests/`); it is covered only through screens.

## Done when
A new `tests/test_investment_figures.py` covers: a balance-only asset lands in Unassigned and the horizons add up to holdings value; a foreign holding's price part and FX part add up to its gain; a holding with no quantity or no gain returns no split. `python -m pytest tests/test_investment_figures.py` passes. No source file changes unless a test finds a real bug; if it does, report it on the GitHub issue first.

Where to look: `lightning/planning/investment_figures.py` (`investment_breakdown`, `_owned_split`, `_native_cost`).
Read first: `tests/test_fx_investments_split.py` for fixtures.
