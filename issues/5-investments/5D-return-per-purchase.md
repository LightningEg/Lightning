---
title: Return per purchase (ROI and CAGR)
type: feature
area: investments
status: blocked
blocked_by: 5B
created: 2026-10-05
by: Claude
---

# Return per purchase (ROI and CAGR)

**Status:** proposal, 2026-10-05 · Claude, not built. Learned from GnuCash (`Gnucash/gnucash` at `53cc9e6`; Lightning at `5665786`). When built, move what holds into [Architecture](../../docs/ARCHITECTURE.md) and delete this file. Needs [investment_lots.md](5B-cost-per-purchase-lots.md).

**They do better:** per purchase, how much it made (ROI) and how fast per year (CAGR), split into sold and still held.

**How they do it** (`investment-lots.scm`): `ROI = gain / basis`; `CAGR = (end value / basis)^(1 / years) − 1`, for realized and unrealized parts.

**Lightning today:** XIRR per holding and for the portfolio (`investments/xirr.py`). Better than GnuCash for money added over time, but nothing per purchase.

**What to change:** after [investment lots](5B-cost-per-purchase-lots.md), add `roi` and `cagr` properties to `Lot` and `Disposal`, shown on lot rows only. XIRR stays the headline. Add both terms to the Glossary.

**Done when:** tests: a single purchase's CAGR equals its XIRR; ROI and CAGR are None for less than a day held or zero basis.
