---
title: London's board returns few UK shares, and Dubai, Abu Dhabi and Bahrain have no month-end history source
type: tech
pillar: own
size: S
model: opus
status: ready
created: 2026-11-04
by: Claude
---

## Report
Found finishing NF-5G (each app fetches its own Gulf and European prices, owner 2026-11-04).

- **London.** TradingView's `uk` screener, asked for the 350 largest stocks (`lightning/market/sources/tradingview.py` BOARDS), answers mostly International Order Book lines (`0Q15` is Abbott, in dollars). The picker list built from it on 2026-11-04 (`python -m tools.market.abroad_catalogue`, Price packs workflow input `catalogue`) kept 58 GBP shares out of 450 London rows after leaving those lines out. The `europe` pack has the same gap.
- **UAE and Bahrain history.** `lightning/market/sources/yahoo.py` SUFFIX has no Dubai, Abu Dhabi or Bahrain entry: one suffix cannot tell Dubai from Abu Dhabi, and Bahrain's is unconfirmed. Their latest closes come from the board, but a missed month-end is not filled from history; it stays in Needs you until typed.

2026-11-08, checked against main: both still true. `lightning/assets/abroad_instruments.csv` has 88 XLON rows: 57 GBP, 28 USD, 3 EUR. `query(board, "stocks")` filters by exchange, type and subtype only, not currency. `yahoo.symbol_for(key)` takes the key alone and SUFFIX has no `AE` or `BH`; the UAE board keys both venues as `AE:` (the second of a same-ticker pair as `AE:EMAAR-XADS`, see `tests/test_market_collector.py` ~line 41), so the venue must come from the asset's MIC: `Want.mic` (`lightning/workflows/live_prices.py` ~line 77) already carries it to the history call (~line 420).

2026-11-10 (O9, Claude): **London done (6F1).** The uk board's stocks request asks for GBX/GBP only; the Price packs catalogue run on the O9 branch rebuilt `abroad_instruments.csv`: 2,037 rows, 376 London shares in pounds (from 57); `tests/test_europe_gcc_coverage.py::test_londons_picker_list_holds_its_own_pound_shares`, `tests/test_market_collector.py::test_london_asks_for_pound_and_pence_shares_only`. **Dubai done.** Yahoo answered `EMAAR.AE` as DFM in AED, so `yahoo.VENUE_SUFFIX = {"XDFM": ".AE"}`; `symbol_for(key, mic)` and `fetch_history(..., mic=)` take the venue, passed from `live_prices.py` (`want.mic`) and `tools/market/collect.py` (`instrument.mic`); fixture `tests/fixtures/market/yahoo_chart_xdfm.json`. **Abu Dhabi and Bahrain still unconfirmed:** `ALDAR.AD`, `ALDAR.AE` and `BATELCO.BH` answered 404, and `NBB.BH` is a US fund (YHD, no currency), so no suffix is guessed.

## Fix
Two steps, one PR each: London's stock request asks for pound/pence listings only, and the picker list is rebuilt (6F1); Yahoo symbols for XDFM, XADS and XBAH come from the venue, once each suffix is confirmed (6F2).

**Read:** [6A](NF-6A-price-packs.md), [6B](NF-6B-europe-and-gcc-shares.md).

## How to work on this item

Each step is one pull request. Read only the files a step names. Tests never touch the network: they use the fixtures in `tests/fixtures/market/`. Run the step's test command, then `python -m pytest tests/test_market_collector.py tests/test_europe_gcc_coverage.py tests/test_live_prices.py -q`; delete the step's heading in the same commit.

## 6F2 Abu Dhabi and Bahrain month-ends from Yahoo, by venue · S · opus · #431
Left (2026-11-10): XDFM is done (see Report); only XADS and XBAH remain. Try other tickers (FAB, ADNOCDRILL, ADCB on Abu Dhabi; AUB, BBK on Bahrain) and suffixes; add a venue to `VENUE_SUFFIX` only when Yahoo's `exchangeName` and `currency` match it, with its fixture, and change the `XADS`/`XBAH` `is None` assertions in `test_yahoo_history_is_put_back_to_the_prices_that_traded`.
Verify first: from a machine that can reach Yahoo (the Price packs workflow can: add a one-off `python -c` to a branch run, or a local network), fetch `https://query1.finance.yahoo.com/v8/finance/chart/<SYMBOL>?range=1mo&interval=1d` for EMAAR on Dubai, ALDAR on Abu Dhabi and BATELCO on Bahrain with the candidate suffixes (`.AE` and `.DU` for Dubai, `.AD` for Abu Dhabi, `.BH` for Bahrain) and keep a suffix only when `chart.result[0].meta.exchangeName` and `currency` (AED, BHD) match the venue. Save one answer per venue, trimmed to 3 days, as `tests/fixtures/market/yahoo_chart_<mic>.json`. **Offline:** do not guess a suffix; write the dated line "suffixes unconfirmed, needs a network run" under Report and stop.
Files: `lightning/market/sources/yahoo.py` (`SUFFIX`, `ZONES`, `symbol_for`, `fetch_history`), `lightning/workflows/live_prices.py` (the `yahoo.fetch_history(session, want.key, ...)` call ~line 420), `tools/market/collect.py` (~line 172), `tests/test_market_collector.py` (`test_yahoo_history_is_put_back_to_the_prices_that_traded`).
Do: add `VENUE_SUFFIX = {"XDFM": ..., "XADS": ..., "XBAH": ...}` with only the confirmed suffixes, and zones `"AE": "Asia/Dubai"`, `"BH": "Asia/Bahrain"`. Give `symbol_for(key, mic="")` and `fetch_history(session, key, since="max", mic="")` a `mic` argument: when `mic in VENUE_SUFFIX`, return the ticker (with any `-<MIC>` ending removed, so `AE:EMAAR-XADS` is `EMAAR`) plus that suffix; without a mic an `AE:` or `BH:` key has no symbol (as today). Pass `mic=want.mic` in `live_prices.py` and the instrument's `mic` in `collect.py`.
Done when: the existing Yahoo test gains `symbol_for("AE:EMAAR", "XDFM")`, `symbol_for("AE:EMAAR-XADS", "XADS")` and `symbol_for("AE:EMAAR") is None`, and a new test parses each saved fixture with the venue's zone and gets dated closes in AED/BHD; `python -m pytest tests/test_market_collector.py tests/test_live_prices.py -q`.
