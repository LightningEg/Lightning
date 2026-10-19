---
title: One table of investment events
type: feature
area: investments
status: ready
created: 2026-10-05
by: Claude
---

# One table of investment events

**Status:** proposal, 2026-10-05 · Claude, not built. Learned from GnuCash (`Gnucash/gnucash` at `53cc9e6`; Lightning at `5665786`). When built, move what holds into [Architecture](../../docs/ARCHITECTURE.md) and delete this file. Build first of the investment designs.

**They do better:** adding an event type is one row in a table, not a new code path.

**How they do it** (`assistant-stock-transaction.cpp`):
1. Each event is one `TxnTypeInfo` row: for units, cash, fees, dividend and gains, a `FieldMask` says enabled or not, which direction, whether zero is allowed, and whether fees are added to cost.
2. **One** validator (`check_page`) and **one** journal builder read the table.
3. A review page shows the balanced journal before posting.
4. The table holds buy, sell, dividend, return of capital, notional distribution, split, reverse split and the short-side versions.

**Lightning today:** `investments/service.py` `_trade_lines` and `_dividend_lines` are separate branches; reinvested dividends, return of capital and bonus shares this way would triple them.

**What to change:**
1. `lightning/investments/events.py`:
   ```python
   @dataclass(frozen=True)
   class EventSpec:
       doc_type: DocType
       units: Sign            # IN, OUT, NONE, NEW_BALANCE
       cash: Sign             # IN, OUT, NONE
       fees: str              # "cost", "proceeds", "none"
       income_category: str | None
       lowers_cost: bool = False

   EVENTS = {
       "buy": EventSpec(DocType.BUY, Sign.IN, Sign.OUT, "cost", None),
       "sell": EventSpec(DocType.SEL, Sign.OUT, Sign.IN, "proceeds", None),
       "dividend": EventSpec(DocType.DIV, Sign.NONE, Sign.IN, "none", DIVIDEND_CATEGORY),
       "reinvested_dividend": ...,   # income, then units at that price, in one document
       "return_of_capital": EventSpec(DocType.SEL, Sign.NONE, Sign.IN, "none", None, lowers_cost=True),
       "bonus": EventSpec(DocType.SPL, Sign.NEW_BALANCE, Sign.NONE, "none", None),
   }
   def lines_for(event, values) -> list[PostingLine]   # the only builder
   def validate(event, values) -> None                  # the only validator
   ```
2. `buy()`, `sell()`, `dividend()` stay as thin wrappers, so routes and tests do not change.
3. The investment entry form shows only the fields the spec enables; the route passes the spec, and the template only reads it.
4. Return of capital lowers open lots' cost by quantity share; any excess over cost is a gain.

**Done when:** every existing investment test passes unchanged; new tests for reinvested dividend and return of capital.
