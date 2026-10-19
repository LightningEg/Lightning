---
title: Market data: price packs, collected in the cloud
type: feature
area: market
status: building
created: 2026-10-05
by: Claude
---

# Market data: price packs, collected in the cloud

Status: proposal, 2026-10-05 (Claude, owner's request). Phase 1 is being built; see *Phases*. When a phase is built, what holds moves into Architecture and this file shrinks.

| Section | Read it when |
|---|---|
| The problem | You want to know why prices change |
| The design in one picture | You need the whole idea in a minute |
| The market file | You read or write the file, or match instruments |
| Packs: choose your markets | You add a market, change a schedule, or work on Settings › Price files |
| Sources, the whitelist | You add, fix or replace a source |
| Checks before anything is published | A price looks wrong, or a source fails |
| Financial assets in the app | You change how an asset is named, classed or edited |
| How the app gets prices | You work on Update prices, first run or a statement import |
| Five months of statements: the history story | You work on back-filling prices |
| Keeping it alive | Something broke, or you plan maintenance |
| Rights and limits | Before publishing the file, or adding a source |
| Phases | You pick up the next piece |

## The problem

Today each copy of Lightning asks Yahoo's undocumented chart feed for each Egyptian stock, one request per stock, at start-up (`lightning/assets/market_data.py`). That means:

- **One source, no fallback.** When Yahoo changes or blocks, every user's prices stop at once, and each user has to wait for a new app version.
- **No funds, no exchange rates, no US stocks.** Fund NAVs, CBE rates and gold are typed by hand.
- **History is fetched live, month by month.** A user who imports five months of statements waits on dozens of requests, and a missed one leaves a hole.
- **Privacy.** Asking Yahoo for exactly the tickers you hold tells Yahoo what you hold.

## The design in one picture

```
 sources (whitelist)          the cloud, after each close          Lightning_Market_Data (open)      each user's app
 ───────────────────          ───────────────────────────          ───────────────────────      ───────────────
 TradingView, Mubasher,  ─▶  collector: adapters, fallbacks,  ─▶  index.json + one folder ─▶  default packs in the ZIP,
 CBE, banks, Yahoo, ...      checks, cross-checks, health          per pack: manifest,          then, when asked, a
                             report; never overwrites good         instruments, monthly         download of only the changed
                             data with bad                         and daily price files        files of followed packs
```

1. **Each app fetches its own prices; the collector is the backup** (owner, 2026-10-05, reversing "the app never scrapes"). CBE now rejects the collector's requests; Banque Misr's dated public transfer rates are the working FX source (owner, 2026-10-07). The app fetches at least at every month-end and on Update prices (*How the app gets prices*). The collector still runs daily after each close: it keeps the shared files a user can download when a source fails for them, and its alarm tells us when an adapter breaks, so the fix ships before most users notice.
2. **One format, one pack per market.** Egyptian stocks, Egyptian funds, exchange rates, US, Gulf and European stocks: each pack is the same format with ISO identifiers, refreshed on its own schedule, and a user follows only the packs they want (owner's request).
3. **History comes with the app.** Each release ships the default packs, so first run and back-filling work offline and at once.
4. **Updating is one button and a few kilobytes.** The app compares checksums and downloads only what changed, usually today's closes.
5. **Nothing depends on the network.** Without it, the app keeps the last file; a user can import a file by hand; typing a price always works and always wins.

## The market file

One folder per pack (*Packs* below), published as files in the open data repository and zipped into each release as `market.zip` (the default packs, one folder each). A pack:

```
market/
  manifest.json          schema, created_at, pack, one entry per file: path, sha256, bytes, rows, first and last date
  instruments.csv        every instrument, its category and its aliases
  monthly/2015.csv ...   one closing price per instrument per month-end, every year we have
  daily/2026-09.csv ...  every daily close, one file per month; the app keeps the last 13 months
  health.json            per source: last good run, failures in a row, rows read, last error
```

**Names follow ISO standards** wherever one exists (owner's request): currencies ISO 4217 (`USD`, `EGP`, and `XAU` for gold), securities ISO 6166 (ISIN), venues ISO 10383 (MIC: `XCAI` for the Egyptian Exchange, `XNAS`, `XNYS`), countries ISO 3166 (`EG`, `US`), dates ISO 8601.

**instruments.csv** — `key,isin,mic,ticker,name,name_ar,category,country,currency,unit,aliases,sources,status,first_date,last_date`

- `key` never changes once published, so it is built from parts that do not move: a listed security is its ISO 3166 country and ticker (`EG:COMI`, `US:AAPL`) because a company can change venue; a fund without a ticker is `EG:FUND:4104` (its Mubasher id); a currency is its ISO 4217 pair, the price of one unit in pounds (`USD/EGP`); gold is `XAU:21K`, EGP per gram of 21K; an index is `EG:EGX30`.
- `isin` (ISO 6166) is filled whenever a source gives it, and it is the first thing the app matches a holding on; `mic` (ISO 10383) is the venue today; `currency` (ISO 4217) is what `close` is in; `country` is ISO 3166 alpha-2.
- `category` is a Lightning asset class: `STOCK`, `FUND.EQUITY`, `FUND.FIXED_INCOME`, `FUND.MONEY_MARKET`, `FUND.GOLD`, `FUND.OTHER`, `CURRENCY`, `GOLD`, `INDEX`. The pickers group by it. (ISO 10962 CFI codes are assigned per instrument by numbering agencies; we add them only when a source publishes them, never by guessing.)
- `aliases` lists old tickers and other names (`STK:COMI`, a fund's Thndr ticker and name), so a renamed or re-listed instrument still matches a user's holding. `sources` lists each source's own id (`mubasher=4104`).
- `status` is `active`, `inactive` (no new price for 30 days) or `delisted`.

**Price files** — `date,key,close`, with `close` in the instrument's currency, six decimals at most, sorted by key and date. Month-end closes are the last close on or before the month's last day. A fund that publishes weekly simply has fewer rows.

**Size.** Measured on a realistic test set the size of all six packs (about 1,100 instruments, month-ends since 2016, 13 months of daily closes): 2.6 MB zipped, 15 MB unpacked; one month of daily closes is about 700 KB raw. An update re-downloads only each followed pack's current month and year files, compressed on the wire (gzip), so a few hundred KB at most.

**Why plain CSV in a folder:** git keeps every version, so our history survives even if a source drops its own; a day's change is a small diff; the app needs no new library; a person can open it.

## Packs: choose your markets

Owner's request (2026-10-05): compile Gulf and European stocks too, let each user choose the exchanges to download and track, publish each in an open repository, and refresh each market on its own schedule. Built in `lightning/market/packs.py` (shared by the app and the collector):

| Pack | What it holds | Venues (ISO 10383) | Trading days | Collected (UTC) | Default |
|---|---|---|---|---|---|
| `egx` | Every EGX stock, the EGX indices | XCAI | Sun–Thu | 13:30 | On |
| `eg-funds` | Egyptian mutual funds' NAV, with fund class | — | Sun–Thu | 19:00 | On |
| `fx` | Banque Misr transfer buy/sell midpoint in pounds | — | Sun–Thu | 13:30 | On |
| `us` | 600 largest US stocks, 100 largest ETFs | XNAS, XNYS, ARCX, XASE | Mon–Fri | 22:30 | Off |
| `gcc` | Every stock on Saudi, Dubai, Abu Dhabi, Qatar, Kuwait, Bahrain and Oman exchanges | XSAU, XDFM, XADS, DSMQ, XKUW, XBAH, XMUS | Sun–Fri | 13:30 | Off |
| `europe` | Largest stocks and UCITS ETFs in London, Xetra, Euronext, Madrid, Milan, Zurich, Nasdaq Nordic | XLON, XETR, XPAR, XAMS, XBRU, XLIS, XMAD, XMIL, XSWX, XSTO, XCSE, XHEL, XICE | Mon–Fri | 17:30 | Off |

- **Published layout:** `index.json` (every pack's name, venues, date, instrument count and download size) and one folder per pack. A pack the app does not know yet still shows in Settings › Price files, by the name the index gives, so a new market needs no new app version.
- **Keys** stay country and ticker of the venue (`SA:2222`, `AE:EMAAR`, `GB:VOD`). One ticker on two venues of one country (Dubai and Abu Dhabi) publishes the second as `AE:EMAAR-XADS`; a published key keeps its venue across runs.
- **Whole units:** prices quoted in pence (`GBX`) or fils (`KWF`) are published in pounds and dinars (ISO 4217).
- **In the app:** Settings › Price files lists every pack with its exchanges, download size and what this computer holds; the profile follows the default packs until it saves its own list (`market_packs`, `none` for none). Unfollowing removes the pack's folder; prices already filled stay. Download shared prices downloads only followed packs; Import a file takes one pack or a release's several, follows what it imports, and skips a pack older than the one held.
- **Other currencies:** Gulf, European and US prices stay in their listing currency and fill only an asset with that same currency. The app values foreign holdings in the profile currency using dated FX; a mismatched quote or missing exchange rate is left explicit, never silently converted.
- **Coverage implemented 2026-10-15:** Oman (`XMUS`) and Nasdaq Nordic (`XSTO`, `XCSE`, `XHEL`, `XICE`) join the existing Europe/GCC boards. Fixture tests cover venue/currency metadata, Nordic underscore tickers, and quote scaling; published keys stay stable. **Unverified live:** the five new board requests received HTTP tunnel 403 under this workspace network policy. Verify their market/exchange identifiers with permitted access before claiming live coverage. Europe/GCC `publish` remains false: the source review below requires permission or a licensed feed before redistribution.

## Sources, the whitelist

Every source has an adapter in `lightning/market/sources/` (shared by the app and the collector), a priority per market, a polite pace (one request every few seconds, a User-Agent that names Lightning), and a recorded sample of its answer for tests. **Verified** means the format is confirmed by working public code or by our own run; the rest are to confirm on the first collector run (this container's network blocks these hosts).

| Market | First | Fallback | Cross-check | History | Notes |
|---|---|---|---|---|---|
| EGX stocks, latest close | TradingView screener: one POST returns every EGX stock (verified, open-source trackers use it) | Mubasher stock list | Yahoo `.CA` chart | Yahoo chart `range=max`, per stock, once; then our own daily files | EGX moves are limited per day, so a jump past the limit needs a second source |
| Egyptian funds, NAV | Mubasher `api/1/funds?country=eg` (verified) | each manager's own page (Banque Misr, CI, AZ, ...) | Starta, EGX Bot fund pages | Mubasher `priceChartFund_{id}.csv`, the whole history in one file per fund (verified) | Mubasher's robots.txt asks bots to keep off `/api/` (see *Rights*); funds split units, so a 1.9× move is a split, not a price |
| Exchange rates | Banque Misr's dated public rate bulletin | CBE if it answers, then NBE | a market-rate feed, labelled "not a bank quote" | our own daily files | Publish the transfer buy/sell midpoint, per one unit; label it Banque Misr, never CBE official |
| US stocks and ETFs | TradingView screener, `america` (verified) | Yahoo chart | Stooq (free key, kept as a GitHub secret) | Yahoo chart `range=max`, once | Prices in USD; valuing them in EGP needs multi-currency (Upcoming projects #15, #16) |
| Gold, EGP per gram | an Egyptian gold-price feed (for example DahabPulse's JSON) | a second gold site | world gold price × a cited USD/EGP rate × karat ÷ 24, labelled "estimate" | the gold site's history | Local retail prices differ from the world price; we say which one we show |
| Indices | TradingView screener | Yahoo | — | Yahoo | For comparisons only (Upcoming projects #1) |

Adding a source is one adapter, one sample, one line of priority, and a test. When a provider changes, the next trading run removes retired providers from current `health.json`; historical prices and their provenance remain.

## Checks before anything is published

A run never publishes a price that fails these; it keeps the last good one and says so in `health.json`.

- **Shape and size:** the answer parses, and has at least as many rows as expected (150 EGX stocks, 100 funds, 10 currencies from Banque Misr). A block page instead of a rate table fails.
- **Sense:** closes above zero, dates not in the future, a "latest" price not older than its market's last trading day by more than a week.
- **Jumps:** a move past the market's limit (EGX stocks 20%, funds 15% unless it is a clean split, currencies 15%) needs a second source that agrees, except a dated first-party CBE or Banque Misr bulletin; its buy/sell spread and rows are checked before it is trusted.
- **Agreement:** when two sources give the same instrument and day, they must agree within 1% (stocks), 0.5% (funds, currencies). If not, the higher-priority source is used only if it also passes the jump check; the disagreement is reported.
- **History is append-only.** A published price is corrected only by a reviewed line in `corrections.csv`, never by a run.

## Financial assets in the app

- **The exchange is a property of the asset, not a new class** (owner's request to show the stock exchange). Each asset gets `mic` (ISO 10383) and `country` (ISO 3166); screens show the exchange's common name: `XCAI` is **EGX**, `XNAS` Nasdaq, `XNYS` NYSE, `ARCX` NYSE Arca. A stock reads "COMI · EGX". Classes stay what the asset is (Stocks, Equity fund, Gold, ...), so allocation and every report keep working, and Investments can split Stocks by exchange later.
- **Edit financial assets** (owner's request): a Financial assets page lists every asset you can hold, with its class, exchange, ISIN and price source, and each opens a form to edit name, ticker, ISIN, exchange, class and whether it is still active. It is Settings › Financial assets, also linked from Investments and the command bar.
- **Matching to the market file:** ISIN first, then country and ticker, then an alias; a match is stored on the asset, and a change of ticker in the file never renames the user's asset without asking.
- **Built (2026-10-05):** migration 0041 adds `mic`, `country` and `market_key` to `financial_assets` (stocks recorded so far became EGX, `XCAI`, `EG:<ticker>`; funds `EG`). `AssetService.create_investment` and `update_investment` check the ISIN's ISO 6166 check digit and the MIC's form, default a stock to EGX, and rename the code when the ticker changes (the asset keeps its id and history). `/investments/assets` lists every holdable asset (not currencies, physical items or price references); it is a Settings page (Settings › Financial assets, beside Valuations), and Investments' Holdings header and the command bar link it; the holding page names the exchange and ISIN.

## How the app gets prices

- **Fetched by the app itself (built 2026-10-05, `workflows/live_prices.py`).** Not daily by itself: month-end closes matter most, as the monthly revaluation is posted from them. Opening a profile fetches only when a held investment lacks the close of a month-end that has passed (open it three days after the month ends and it gets that month-end's close), at most once a day. Update prices fetches at any time: latest closes and every missing month-end. Latest closes come from whole boards (TradingView's EGX board, Mubasher's fund list), so asking reveals nothing about what you hold; month-end closes from each instrument's history (Yahoo for stocks, Mubasher for funds), the last close within ten days before the month-end. A close counts only once final (during trading hours the moving price is skipped). Saved as `ONLINE`; a typed price wins. Funds need their Mubasher key (phase 3 matches them); stocks in another currency than the holding wait for multi-currency; exchange rates wait for FX revaluation (phase 4), with Banque Misr's adapter ready.
- **Funds by name, gold by the world price (built 2026-10-06).** A held fund without its Mubasher number is matched by exact name against the fund list the app already downloads, or its Mubasher page is pasted on Edit investment. Gold (the 18K, 21K and 24K references and gold held by the gram) is Yahoo's world price (GC=F) ÷ 31.1035 × the dollar (EGP=X) × karat ÷ 24, said to be an estimate; an Egyptian shop-price source is still to choose and test from a home connection. Silver is not held in Lightning yet.
- **Never in the way (built 2026-10-06).** The fetch on opening runs in the background; the next page saves it and says "Month-end prices: …". Prices still missing show on Investment prices with Get prices (ask again); after two failed tries it also offers Use shared prices. Settings › Price files › Test price sources asks each source once and names any that fails.
- **The shared files, opt-in.** If a source fails for you, Investment prices › Download shared prices brings the collector's files for the markets you follow.
- **The bundled file.** Each release carries `market.zip` with the default packs. On first run, after an import, and every month-end, the app fills prices from it for the instruments the profile holds. Manual prices still win.
- **Download shared prices.** One button downloads `index.json` and, for each followed pack, its `manifest.json` from the open data repository (setting `market_url`, default `Lightning_Market_Data`), compares checksums with the profile's copy (`<profile>/market/<pack>/`; sharing one copy between profiles is a later step), downloads only the changed files, checks them all before writing any, and fills. After the first time, a month of updates is about 1 MB per pack.
- **Import a file.** Investment prices takes a `market.zip` by hand (40 MB at most in the desktop window), for an offline PC or when the address moves.
- **Built (2026-10-05):** the Price files card on Investment prices (now Fill from price files, Download shared prices, Import a file), Settings › Price files, `lightning/workflows/market_prices.py` (matching: ISIN, saved key, alias, country and ticker), `lightning/market/update.py`; prices are saved with source `MARKET`. Measured on a realistic test file of all six markets' size in one: about 2.6 MB zipped, 15 MB unpacked.
- **Say how old it is.** Every price shown from the file carries its date; Needs you says "Prices are from 2026-10-01" when they are a week old, as today.
- **Same file for everyone.** Downloading the whole file tells no one what you hold.

## Five months of statements: the history story

Mohab imports THNDR statements from May to September. For each holding and month-end he needs a price:

1. The importer lists the (instrument, month-end) pairs it needs.
2. It fills them from the local market file at once: monthly closes reach back to 2015, daily closes 13 months.
3. What the file lacks (a fund we do not cover, a stock listed after the file was made) goes to Needs you: "2 prices missing: Misr Takaful Fund, July and August · Enter prices". Never a zero, never a guess.
4. Update prices can fill the rest later; a typed price stays.

This is why history ships in the file: it turns a minute of live requests that may fail into an instant, offline lookup.

## Keeping it alive

- **Small adapters with samples.** When a site changes, one adapter's test fails against the new sample, and the fix is local.
- **Fallbacks and cross-checks** per market, so one broken source lowers confidence instead of stopping prices.
- **Health and alarms.** Two failed runs in a row open a GitHub issue naming the source and its error; recovery closes it. The app shows the file's age, so a stale file is visible.
- **Our own history.** Because every day is kept in git, losing a source loses future prices from it, never past ones.
- **The address can move.** The app reads the manifest address from a setting with a built-in default, and Import a file always works.
- **Schedules keep running.** GitHub disables scheduled workflows after 60 days without activity; the daily data commit counts as activity.
- **Built (2026-10-05):** `.github/workflows/market-data.yml` runs a schedule per market close (13:30 UTC Egypt and Gulf, 19:00 funds, 17:30 Europe, 22:30 US; `tests/test_market_collector.py` keeps them in step with `packs.py`), tests the collector first, and publishes to the data repository only when the variable `MARKET_PUBLISH` is `true` and the secret `LIGHTNING_MARKET_TOKEN` exists; until then each run checks every source and keeps its packs as a seven-day artifact. `python -m tools.market alarm` lists sources failing twice in a row, which open an issue; a good run closes it.

## Rights and limits

These need the owner's decision before the file is published:

- **Mubasher** asks automated clients not to use `/api/` in its robots.txt (as the open-source funds tracker reports). Use it at most once a day, or ask Mubasher for permission or a feed.
- **TradingView and Yahoo** terms forbid automated collection and republishing. They are fine as cross-checks a user's own app performs, but publishing their data in our file is a risk, more so in a paid app.
- **EGX** licenses its market data; republishing end-of-day prices in a commercial product may need a licence or a licensed vendor (EGX data vendors, or paid APIs with redistribution terms).
- **FX rates:** the CBE endpoint rejects the collector. Banque Misr's public bulletin supplies transfer buy/sell quotes; publish only the numeric midpoint with attribution and its bulletin date, and revisit the source if its terms or access change.
- **Fund NAVs** are public disclosures by each manager; the manager's own page is the cleanest source.

**Decided (owner, 2026-10-05; FX source revised 2026-10-07):** publish only what a source allows, and cite every source. Each pack in `packs.py` names its `source` (written into its manifest and `index.json`, and shown on Investment prices and Settings › Price files) and whether it may be `publish`ed. Today only `fx` (Banque Misr) is published and shipped in the release ZIP; the other packs are collected and checked, kept only as the run's artifact. A fund-manager adapter, a source's written permission or a licensed end-of-day feed turns another pack on.

## Phases

1. **Now:** this proposal; the file format with ISO names (`lightning/market/`); the collector with adapters, checks and health (`tools/market/`); exchange and ISIN on financial assets, with a Financial assets page to edit them; packs and Settings › Price files; filling, updating and importing on Investment prices; the scheduled workflow, publishing only after the owner's go-ahead (all built).
2. **Built 2026-10-05:** the release ZIP carries `market.zip` (`python -m tools.market release`, required for a tagged release, so a release waits until the packs are published); opening a profile (first run, newer file, new month) and a brokerage statement import fill month-ends (`workflows/market_prices.fill_if_due`, `fill_followed`); Needs you lists what is missing until typed; the per-user Yahoo code (`assets/market_data.py`) is removed.
3. Funds, currencies and gold matched to profile holdings; reviewed Thndr-to-Mubasher fund mapping.
4. US stocks and FX revaluation, with multi-currency (Upcoming projects #15, #16).
