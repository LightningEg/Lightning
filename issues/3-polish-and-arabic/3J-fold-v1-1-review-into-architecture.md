---
title: Version 1.1 is shipped: move what holds of its review into Architecture, then delete this file
type: tech
area: docs
status: ready
created: 2026-10-13
by: Claude
---

# Version 1.1: presentable, smarter FX, US stocks

Claude's review, 2026-10-13, of what was built after 1.0 beta 1 (2026-10-07) and of the FX mechanism, with the work that turns the beta into a presentable 1.1. Two work packages: **A** (brand and US stocks) and **B** (FX). Once built, move what holds into Architecture and delete this file.

## 1. Brand review of what is new since the beta

New since the beta (Codex 10-10, Luna 10-09, Claude 10-12): spreadsheet register, Currencies tab and Settings › Currencies, sticky top bar and full screen, busy toast, success toasts, Cash at hand, expense-intensity calendar, profile currency at setup, welcome currency, sample stories, Arabic UI.

Checked with a browser audit of the computed styles on 15 PC pages with the Mohab sample (1440 px), plus screenshots. Upper-case text: none visible (the old `text-transform` rules are overridden). Headers H1/H2 are Ink. What fails:

| # | Finding | Rule | Where |
|---|---|---|---|
| 1 | Ordinary spending amounts are **Strong rose** text (`−90`, `−3,251`). Strong rose is only for *needs you*; Soft rose is never text. Spending reads Ink with its minus; the row's rose mark carries the meaning | A03, A03.3, A16 "colour off its meaning" | Register (`/transactions`, `/accounts/<id>`), changelog 10-10 "negative amounts use rose" |
| 2 | Links are **Azure, not underlined** (52 on `/transactions`, 41 on an account) | A03.3: links are Ink and underlined, never Azure | global `a { color: var(--accent) }`, `.metric-link`, sidebar "+ Add account" |
| 3 | Text in colours outside A03: `#0B8A5F` (a Green step, used as text: Overview net flow, Investments/Budget %), `#073D2A` (Overview chart labels), `#3A1022` (Expenses "Loan payments"), `#8A5A00` amber ("One-off" pill on Categories) | A03 | `style.css` |
| 4 | H3 headers in **Muted** | A05/A16: headers are Ink | Settings, Budget, Financial health, Investment prices (`h3 { color: var(--muted) }`, line 49) |
| 5 | **White fields**: the sidebar search input, the profile chooser's Language select (white, boxed) | A10.3: soft wells, never white | `base.html` search, `profiles.html` |
| 6 | Register is **wider than its card at 1440 px**: the Balance column is cut off and scrolls inside | A09 one screen | `/transactions` |
| 7 | **Dropdowns for long lists**: profile currency at setup and on the welcome screen is a `<select>` of ~180 ISO codes; Categories rows use 34 selects | A10.3: type and pick | `profiles.html`, welcome, `/categories` |
| 8 | Sidebar caption reads "Balances inEGP" (missing space) | A14 words | sidebar partial |
| 9 | Two palettes live in `style.css`: the legacy `:root` (ink `#0B2239`, coral `#B8382F`, teal, `--grad-horizon` with teal in the middle) and the guideline layer at line 835 (`--pos #08764F`, `--neg #A82F5D`, both off A03). Dark mode still paints `.card`, `.topbar`, `.side` with gradients | A03, A03.2 (vivid gradient brand only, two stops), B09 | `style.css` |

Not yet audited and part of package A: the phone frame (Part C) for the same new screens, Arabic (`style.rtl.css` is generated: change the English file, run `tools/build_rtl_css.js`), dialogs and toasts.

## 2. The FX mechanism today

Built (`lightning/fx.py`, `transactions/service.py::_fx`, `reporting/valuation.py::_fx`, `reevaluations.py`, migration 0049): registered currencies, a profile base, foreign cash accounts, manual dated rates (`fx_rates`, source `MANUAL`), month-end FX revaluation (`VAL`) for foreign cash, Currencies tab with native and profile values.

What is missing or weak, most important first:

1. **You cannot buy dollars.** A transfer between an EGP and a USD account is refused ("moving money between currencies is not built yet"). This is the first thing an Egyptian with dollar savings does. `DocType.CNV` is reserved and unused.
2. **Rates are typed by hand only.** The `fx` price file (Banque Misr midpoints) is collected and published but never reaches `fx_rates`; `live_prices` already fetches Yahoo `EGP=X` for gold and throws the rate away.
3. **Any old rate is used silently.** `latest_fx` takes the last rate on or before a day with no age limit: a rate from March values a balance in October without a word.
4. **Only one direction.** A rate is looked up as `foreign → base` only. A USD profile cannot use the EGP-quoted price file, and EUR via EGP (cross rate) is impossible.
5. **No cost of your dollars.** Nothing keeps what you paid for the foreign money you hold, so there is no unrealized or realized FX gain, no average rate, and the spread you paid at the bank is invisible.
6. **Foreign investments are booked in the base currency.** `AssetService.create_investment` always sets `currency = base_currency`, so a Nasdaq stock is an EGP asset: its USD price is refused ("priced in another currency, left for you") and its return mixes price and FX.

## 3. US stocks today

The pieces exist but do not connect: venues `XNAS/XNYS/ARCX/XASE` (`market/iso.py`), the `us` price-file definition (`market/packs.py`, `publish=False`: TradingView and Yahoo terms forbid republishing, owner decision 2026-10-05), `live_prices.instrument_key` maps `US:` keys to the `us` pack and Yahoo, and the collector checks `tradingview-us`. Missing: a **US list to pick from** (the picker's catalogue `assets/egx_instruments.csv` is EGX and Egyptian funds only), the **asset's currency from its exchange** (see 2.6), and returns split into price and FX.

## 4. Design

### 4.1 Conversion (package B)

*Convert* in the account's actions: from account, to account (different currencies), amount sent, amount received, optional fee (in the sending currency). Posted as one `CNV` transaction:

- sending line: `−sent` at the day's rate of the sending currency (`INTERNAL`);
- receiving line: `+received` at the **executed rate** `sent_base ÷ received` (≤ 6 places), so internal lines net to zero in the base and the received dollars carry what they really cost, spread included;
- fee: an `OUTFLOW` line in *Fees & Charges*.
- If rounding leaves a cent between the two base amounts, put it on the receiving line's rate choice or a zero-quantity rounding line; `validate_posting` must pass with no `Other`.
- The form shows the executed rate and, when a reference rate exists for that day, the spread against it ("0.6% above Banque Misr's 47.85"). A missing reference rate never blocks a conversion: the executed rate is itself a dated rate (save it as source `TRADE`).

The register shows one row with both amounts; edit and void work as for transfers. Bank import and SMS keep producing transfers; matching a pair across currencies is a later step.

### 4.2 Rates that arrive by themselves (package B)

- Fill `fx_rates` from the followed `fx` price file (source `MARKET`) and from `live_prices` (Yahoo `<CCY>EGP=X`, source `ONLINE`) for every registered currency. Order of trust on a day: `MANUAL` > `TRADE` > `MARKET` > `ONLINE` (`docs/proposals/price_source_order.md`).
- One lookup function for all callers (transactions, valuation, reevaluation): direct, else inverse (`1 ÷ rate`), else cross through EGP. Rates are stored as quoted; derived rates are never stored.
- Age: a rate older than **10 days** for a day still values the balance but is shown as *as of <date>*, and a rate older than **45 days** is *missing* (Needs you), matching how prices behave (`MAX_GAP_DAYS`). Check the existing gap rule before choosing the numbers; one rule for prices and rates.

### 4.3 FX positions (package B): the Currencies tab becomes the analysis

The Currencies tab (`/accounts/currencies`, under Overview) stays one tab (two levels, at most five tabs) and shows, per foreign currency (four, then Other):

| Figure | Meaning |
|---|---|
| Held | Native units across accounts (cash) and, separately, foreign investments at market |
| Value | Held × today's rate, in the base |
| Average rate | Base cost ÷ units still held, average cost: conversions add units at the executed rate; money in (salary in USD) adds at the day's rate; spending and conversions out remove units at the average |
| Unrealized FX gain | Value − base cost of what is still held |
| Realized FX gain | For units that left: (day's rate − average rate) × units, for the selected period |
| Spread paid | Executed − reference rate on conversions, for the period |

Plus one chart: the base value of the currency's holdings against its cost line by month (A12; held = Azure, cost dashed Neutral). KPIs toned by meaning (gain Meadow text, loss Strong rose only when it needs you, else Ink with sign). Rows link to the account register. Calculations live in a Python service (`lightning/reporting/fx_positions.py`), never the template.

Reconciliation rule for the tests: for a currency, *unrealized + realized since the first holding* = the sum of that currency's FX `VAL` journals + the change since the last month-end. Write it as a test.

### 4.4 US stocks (package A)

- **List**: `lightning/assets/us_instruments.csv`, same columns as the EGX file plus `mic,currency`: the largest US stocks (about 300) and ETFs (about 60: broad market, sector, bonds, gold, dividend, international), names as listed. The container has no route to TradingView, Nasdaq or Yahoo, so build the first list from known large caps, mark `source` as `compiled list` and `catalogue_date`, and add `tools/market/us_catalogue.py`, which rebuilds it from the TradingView `america` scanner the collector already uses, for the owner or CI to refresh. `assets/catalog.instruments()` returns both files; the picker filters by exchange.
- **Currency follows the exchange**: a `VENUE_CURRENCY` map beside `VENUES` (US → USD, XLON → GBP (pence: GBX handling noted, not built), XETR/Euronext → EUR, XSWX → CHF, Gulf venues → SAR/AED/QAR/KWD/BHD, XCAI → EGP). `create_investment` sets the asset's currency from it and registers the currency if needed. A US stock needs a USD brokerage account (or a USD cash account to pay from) and a USD rate; the buy form says so in one line when one is missing.
- **Prices**: with the asset in USD, `live_prices` (Yahoo, already wired) and typed prices work; nothing is republished (the `us` file stays `publish=False`).
- Mohab: a USD brokerage account, one Nasdaq ETF bought with dollars from a conversion, in the 2026 sample and in `tests/test_mohab_year.py`.

### 4.5 Foreign holdings: price and FX apart (package B, after A's currency step)

On Investments, a foreign holding's unrealized gain splits into **price** = (value − cost) in its currency × today's rate, and **FX** = cost in its currency × today's rate − cost in the base. The two add up to the base unrealized gain. The Glossary already names *Unrealized gain*; add *FX part* and *Price part* (Overview #16).

## 5. Work packages

Each package: own branch, small tested steps, push each; CSS only from the guideline; Mohab + A16 for visible changes; changelog ≤ 3 lines per entry; Glossary for new figures; Architecture when built.

**A — brand and US stocks** (`claude/v1-1-brand-and-us-stocks`)
1. Findings 1–9 above, PC; regenerate the RTL CSS; extend the audit into a test that fails on Azure links, off-palette text, uppercase, Muted headers and white fields on the main pages (`tests/test_brand_audit.py`, skipped when Playwright is absent).
2. Phone (Part C) and Arabic pass on the same screens; `tools/phone_check.py` clean.
3. 4.4: venue currency, US list and picker, Mohab step.
Files: `lightning/ui/static/*.css` (not the FX block), `lightning/ui/templates/` (not `accounts/currencies*`, not the convert form), `lightning/assets/`, `lightning/market/iso.py`, `tools/market/us_catalogue.py`.

**B — FX** (`claude/v1-1-fx`)
1. 4.2: one rate lookup (direct, inverse, cross, age); fill from the `fx` file and `live_prices`.
2. 4.1: conversion (`CNV`) service, route, form, register row, tests.
3. 4.3: `fx_positions` service and the Currencies tab.
4. 4.5 once A3 is on main.
Files: `lightning/fx.py`, `lightning/transactions/`, `lightning/reporting/` (new `fx_positions.py`, `valuation.py`, `queries.py`), `lightning/reevaluations.py`, `lightning/workflows/live_prices.py`, `lightning/workflows/market_prices.py`, `lightning/investments/report.py`, routes/templates for currencies and convert. New CSS only in a block at the end of `style.css` headed `/* FX positions and conversion (v1.1) */`.

## 6. For the owner

- Version number: when both packages are on main and green, bump to `1.1.0` and build Windows and Android (the build workflows are run by hand).
- The US list is compiled, not downloaded; refresh it with `tools/market/us_catalogue.py` where TradingView is reachable.
- Rate age limits (10 and 45 days) are a proposal; say if you want others.
