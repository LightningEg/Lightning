---
title: Cost per purchase (lots)
type: feature
area: investments
status: blocked
blocked_by: 5A
created: 2026-10-05
by: Claude
---

# Cost per purchase (lots)

**Status:** proposal, 2026-10-05 · Claude, not built. Learned from GnuCash (`Gnucash/gnucash` at `53cc9e6`; Lightning at `5665786`). When built, move what holds into [Architecture](../../docs/ARCHITECTURE.md) and delete this file. Build after [investment_events.md](5A-one-table-of-investment-events.md).

**They do better:** each purchase keeps its own cost and date, so a sale shows which purchases it used up, the gain on each and how long each was held.

**How they do it** (`libgnucash/engine/`):
1. Every buy opens a **lot** (`gnc-lot.cpp`).
2. A **policy** object picks the lot a sale comes from (`policy.cpp`): FIFO (oldest first), LIFO (newest first), average, or manual.
3. A sale bigger than the lot it hits is **cut into two pieces**, one that closes the lot and one carried to the next (`cap-gains.cpp` `xaccSplitAssignToLot`, line 219).
4. Each piece gets its own realized gain (`xaccSplitComputeCapGains`).
5. Lots are **stored**, so a back-dated edit leaves them stale; a "gains dirty" flag and scrubbers (`Scrub3.cpp`) repair them, and their own comment warns of "a potential trickle-through effect on all later lots".

**Lightning today:** `investments/service.py` `portfolio()` (lines 337–410) replays every investment line and keeps **one average-cost pool** per account, asset and owner. Right for funds and what Egyptian brokers show, but no per-purchase cost, gain or holding period.

**What to change** (derive lots, never store them, so there is nothing to scrub):
1. New pure module `lightning/investments/lots.py`:
   ```python
   @dataclass
   class Lot:          # one purchase, or what is left of it
       opened: str; quantity: Decimal; cost: Decimal; owner_id: int | None
   @dataclass
   class Disposal:     # one piece of a sale against one lot
       lot_opened: str; sold: str; quantity: Decimal; cost: Decimal; proceeds: Decimal
       gain = property(lambda self: self.proceeds - self.cost)
       days_held = property(...)
   def build_lots(lines, method="average") -> tuple[list[Lot], list[Disposal]]
   ```
2. `average` is one lot that absorbs every buy: exactly today's numbers. `fifo` takes from the oldest open lot and cuts a sale across lots; proceeds are shared by quantity and the last piece takes the rounding remainder so the pieces add up to the sale.
3. `portfolio()`'s inline pool loop (lines 360–375) becomes a call to `build_lots`. `Position` gains `lots` and `disposals`; `cost_basis` and `realized` become sums over them.
4. Migration: `accounts.cost_method TEXT NOT NULL DEFAULT 'average'`, shown on the account edit page for brokerage accounts only.
5. Later, only if asked: choose the exact purchases a sale uses (GnuCash "manual"), as `sale_lot_picks(transaction_id, lot_opened, quantity)` read by `build_lots`.

**Done when:** with `average`, every existing investment test and Mohab's test give the same numbers (the refactor guard); new tests for FIFO across three buys and a sale that spans two lots; the pieces always add up to the sale.
