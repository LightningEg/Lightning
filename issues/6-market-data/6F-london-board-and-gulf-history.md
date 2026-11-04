---
title: London's board returns few UK shares, and Dubai, Abu Dhabi and Bahrain have no month-end history source
type: tech
pillar: own
size: M
status: new
created: 2026-11-04
by: Claude
---

## Report
Found finishing NF-5G (each app fetches its own Gulf and European prices, owner 2026-11-04).

- **London.** TradingView's `uk` screener, asked for the 350 largest stocks (`lightning/market/sources/tradingview.py` BOARDS), answers mostly International Order Book lines (`0Q15` is Abbott, in dollars). The picker list built from it on 2026-11-04 (`python -m tools.market.abroad_catalogue`, Price packs workflow input `catalogue`) kept 58 GBP shares out of 450 London rows after leaving those lines out. The `europe` pack has the same gap.
- **UAE and Bahrain history.** `lightning/market/sources/yahoo.py` SUFFIX has no Dubai, Abu Dhabi or Bahrain entry: one suffix cannot tell Dubai from Abu Dhabi, and Bahrain's is unconfirmed. Their latest closes come from the board, but a missed month-end is not filled from history; it stays in Needs you until typed.

## Fix
- Ask the `uk` board for GBX-quoted listings only (a currency filter in `query()`), rebuild `lightning/assets/abroad_instruments.csv` with the catalogue workflow, and check the London count in `tests/test_europe_gcc_coverage.py`.
- Find a history source for XDFM, XADS and XBAH (Yahoo's suffixes confirmed from a permitted network, or the exchanges' own end-of-day files), then add them to SUFFIX with a fixture test in `tests/test_live_prices.py`.

**Read:** [6A](6A-price-packs.md), [6B](6B-europe-and-gcc-shares.md).
