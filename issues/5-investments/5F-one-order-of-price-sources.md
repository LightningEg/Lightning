---
title: One order of price sources
type: tech
area: investments
status: ready
created: 2026-10-05
by: Claude
---

# One order of price sources

**Status:** proposal, 2026-10-05 · Claude, not built. Learned from GnuCash (`Gnucash/gnucash` at `53cc9e6`; Lightning at `5665786`). When built, move what holds into [Architecture](../../docs/ARCHITECTURE.md) and delete this file.

**They do better:** when two prices exist for one day, which one wins is a single written rule.

**How they do it** (`libgnucash/engine/gnc-pricedb.h`, line 166): every price has a source from a ranked list (editor, online quote, user, transfer, register, import, split, transaction…); a higher source overwrites a lower one that day, never the reverse.

**Lightning today:** `price_history` is unique on `(asset_id, date, source)`, so one day can hold several prices; `reporting/valuation.py` chooses by its own branches (manual value, then reference).

**What to change:** one `SOURCE_RANK` tuple in `reporting/valuation.py` (manual, then trade, then the market pack's sources, then cost) used by every lookup, replacing the branch order.

**Done when:** tests: a manual price beats the pack's price that day; the pack's later price beats an older manual one; a trade price counts for its own day.
