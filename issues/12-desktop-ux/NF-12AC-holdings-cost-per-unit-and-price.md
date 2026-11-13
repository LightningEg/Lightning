---
title: The holdings table shows cost per unit (weighted average) and the current price for each investment
type: feature
pillar: understand
size: M
model: sonnet
status: new
created: 2026-11-12
by: owner
---

## Report
Owner, 2026-11-12: the holdings table (Investments) shows Cost, Value, Total gain and Total return only. It needs the cost per unit (the weighted average of what was paid) and the current price per unit beside them, for stocks and funds.

## Fix
Add two columns to the holdings table, PC and phone, from Python (the figures live in `lightning/investments`, never the template): cost per unit = cost / units held, current price = last price. Whole-EGP rule A16 does not apply to a price: show two decimals, four under 1. Register both names in the Glossary. Test: a holding bought in two lots shows the weighted average.
