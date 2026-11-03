---
title: One table of investment events
type: feature
pillar: own
size: L
status: ready
created: 2026-10-05
by: Claude
---

# One table of investment events

**Status:** proposal, 2026-10-05 · Claude. 5A1 built 2026-11-02 (`lightning/investments/events.py`: `EventSpec`, `EVENTS` with buy, sell and dividend, `lines_for`, `validate`; the service's `_trade_lines` and `_dividend_lines` call them); 5A2 built 2026-11-02 (`InvestmentService.record(event, ...)` is the one recording path; `buy`, `sell`, `dividend` and `update` call it; `_event_lines` replaced `_trade_lines` and `_dividend_lines`); 5A3 built 2026-11-02 (`events.form_fields(event)`; the route passes it as `spec`, `investments/form.html` only reads it); 5A4 half built: the reinvested dividend (`reinvested_dividend` row; income, tax, then units for the net in one DIV document; portfolio, investment report and holding journey read it); return of capital waits for an owner decision. Learned from GnuCash (`Gnucash/gnucash` at `53cc9e6`; Lightning at `5665786`). When built, move what holds into [Architecture](../../ai/ARCHITECTURE.md) and delete this file. Build first of the investment designs.

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

## 5A4 Return of capital · M
Needs 5A1 and 5A2 merged first. **Owner decision needed before building** (the reinvested dividend half is built, 2026-11-02: `reinvested_dividend` row, tests in `tests/test_investment_events_table.py`). Return of capital lowers open lots' cost by quantity share, and any excess over cost is a gain. The row the item sketches (`SEL`, no units, cash in) cannot post today: `validate_posting` refuses a zero-quantity line and `ledger_entries` has `CHECK (effect='REVALUATION' OR quantity_e6<>0)`, and internal lines must net to zero. Choices:
- **A. Allow a zero-unit, cost-only line** (migration rebuilding `ledger_entries` like 0013, relax `validate_posting`): cash +X internal, units line quantity 0 and amount -X. Cost and gain stay in the ledger; the three average-cost engines (`portfolio`, `investment_period`, `_realized_between`) each need a zero-quantity branch. Most honest, largest change.
- **B. Cash as income, cost lowered by a revaluation-style line:** cash +X in a "Return of capital" category plus a zero-unit REVALUATION line of -X on the asset. No schema change, but the cash counts as income in cash-flow reports unless that category is carved out.
- **C. Cash internal plus a one-smallest-unit sell line:** no schema change but fakes a sale and a quantity.
Also decide: does the excess over cost count as a realized gain (item text) or as income?
