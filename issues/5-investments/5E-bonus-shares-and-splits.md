---
title: Bonus shares and stock splits
type: feature
area: investments
status: blocked
blocked_by: 5A, 5B
created: 2026-10-05
by: Claude
---

# Bonus shares and stock splits

**Status:** proposal, 2026-10-05 · Claude, not built. Learned from GnuCash (`Gnucash/gnucash` at `53cc9e6`; Lightning at `5665786`). When built, move what holds into [Architecture](../../docs/ARCHITECTURE.md) and delete this file. Needs [investment_lots.md](5B-cost-per-purchase-lots.md) and [investment_events.md](5A-one-table-of-investment-events.md).

**They do better:** a split or bonus issue is its own event: units change, cost does not, and no fake purchase appears.

**How they do it:**
1. Split and reverse split are types in the stock assistant (`gnucash/gnome/assistant-stock-transaction.cpp`, line 273).
2. The user types the **new number of units**, not a ratio (`FieldMask::INPUT_NEW_BALANCE`).
3. When balances are recomputed, every earlier quantity is rescaled by `new balance / old balance` into an `adjusted_amount`; cost is left alone (`Account.cpp` around line 2285).
4. Cash for fractions is recorded as a sale **first**, then the split (the assistant's own instruction).

**Lightning today:** EGX companies often give bonus shares (أسهم مجانية). The only way is a buy at price 0, which shows as a purchase in the list and adds a false flow to XIRR.

**What to change:**
1. `DocType.SPL = "SPL"` ("Bonus or split") in `core/refs.py`: one units line, `amount_base_e6 = 0`, no cash line, no category, no effect on spending or income.
2. `build_lots` ([investment lots](5B-cost-per-purchase-lots.md)): on an SPL line, `ratio = (held + q) / held`; multiply every open lot's quantity by it, keep cost.
3. XIRR skips it (no money moved).
4. The price chart divides prices before the split date by the cumulative ratio when it builds the series (Python), so the line does not fall off a cliff. Stored prices stay as they are.
5. Form: "Units you hold after" (prefilled with today's holding), date, notes. Built as an event in [investment events](5A-one-table-of-investment-events.md).

**Done when:** tests: 100 units at 10, a 1-for-4 bonus, 125 units, cost unchanged, average cost 8; a reverse split; a sale after the split gives the right gain; XIRR unchanged by the split.
