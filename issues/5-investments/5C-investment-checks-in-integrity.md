---
title: Investment checks in the integrity screen
type: feature
area: investments
status: blocked
blocked_by: 5B
created: 2026-10-05
by: Claude
---

# Investment checks in the integrity screen

**Status:** proposal, 2026-10-05 · Claude, not built. Learned from GnuCash (`Gnucash/gnucash` at `53cc9e6`; Lightning at `5665786`). When built, move what holds into [Architecture](../../docs/ARCHITECTURE.md) and delete this file. Needs [investment_lots.md](5B-cost-per-purchase-lots.md).

**They do better:** a report tab that finds broken investment records.

**How they do it** (`gnucash/report/reports/standard/investment-lots.scm`, Validation tab): it flags lots with a negative balance, lots with more than one purchase, sales not assigned to a lot, and gains that do not match.

**Lightning today:** `integrity.py` checks balances, budgets and the net-worth bridge; nothing about holdings. `_check_holdings` guards new posts and voids, but not every back-dated edit path.

**What to change:** in `IntegrityService.checks()` add:
1. *Lots add up:* per position, sum of lot cost = `cost_basis`, sum of lot quantity = `quantity`.
2. *Never sold what was not held:* replay each holding by date and flag the first day its quantity goes below zero.
3. *Sales add up:* sum of disposal gains = `realized`.

**Done when:** tests break each rule on purpose with direct SQL and the check reports it; Mohab's year passes all three.
