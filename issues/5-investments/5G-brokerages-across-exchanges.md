---
title: Brokerages that span exchanges and currencies - structure, workflows and analysis to build
type: feature
area: investments
status: building
created: 2026-10-15
by: Claude
skills: none
app_version: 1.1.0b1
commit: 08bb699
repo: app
---

## Report

**Brief from the owner:** we are adding many stock exchanges. One brokerage can trade on several exchanges, so it will
hold several currencies. Think through the whole workflow (how brokerages and exchanges are set up, used and analysed),
look at the big picture and say what we should do. Nothing is built here. Companion report on the rest of the app:
[2026-10-15-product-one-organism-audit.md](../3-polish-and-arabic/3G-one-organism-review-of-every-tab.md).

**How I looked.** Main `08bb699` with Mohab's sample (`THNDR` in EGP with EGX stocks and a fund; `Dollar brokerage` in
USD with QQQM on Nasdaq). I read the investment, asset, market, FX and currency code, the ledger rows in
`data/sample.db`, the account, holding, prices and price-files screens, and `issues/6-market-data/6A-price-packs.md` (6A),
`investment_events.md` and `investment_lots.md`.

---

### 1. The short answer

1. **A brokerage is one account on screen, with one cash pocket per currency inside it.** Holdings sit in the pocket of
   the currency they trade in. Under the hood a pocket is a child account with a single currency. That keeps the rule
   the whole ledger relies on ("one account line, one currency", used at about 100 call sites) and still gives the user
   one broker, one total and one statement to reconcile.
2. **Currency belongs to the listing, not the exchange.** A listing is a security (ISIN) on an exchange (MIC) in a
   trading currency, with a price scale for pence (GBX) or fils (KWF). Today the currency comes from the exchange, which
   is wrong for London, for some EGX lines and for dollar funds.
3. **Markets are picked per brokerage and defaulted from the institution.** Holding something on a market follows that
   market's prices automatically; the *Price files* page stops being a setup step.
4. **Every investment figure has two lenses:** its own currency ("did the investment work?") and EGP ("did it make me
   richer?"). The gap between them is the pound's effect. For an Egyptian investor that is often the biggest number on
   the page, and Lightning can show it better than anyone.
5. **Analysis gets five views of the same holdings:** by asset class (exists), by account, by currency (Gulf currencies
   grouped with the dollar they are pegged to), by market or country, and by security (merged across brokers).

### 2. How it works today

| Fact | Where |
|---|---|
| An account has one currency. A trade is refused unless the asset, the holding account and the cash account share it | `accounts.currency`; `InvestmentService._same_currency`, `lightning/investments/service.py:472` |
| Broker cash is a `CASH:<ccy>` line inside the brokerage account; a buy must use cash already in that account | `service.py:455`, `:510` |
| An asset's currency is its exchange's currency; unlisted funds, gold and certificates are always EGP | `lightning/assets/service.py:193-195`, `lightning/market/iso.py` `VENUE_CURRENCY` |
| Each ledger line keeps the amount in the account currency, the FX rate and the EGP amount, so native and EGP cost both exist | `ledger_entries.amount_e6`, `fx_rate_e6`, `amount_base_e6` |
| FX: dated rates, cross rates through EGP; CBE and Banque Misr cover 18 currencies | `lightning/fx.py` (`PIVOT`), `lightning/market/sources/cbe.py` |
| Every currency's cash is created with 2 decimals | `lightning/database/currencies.py:61-63` |
| Unrealised gain on a foreign holding is split into price and FX | `investments/report.py::foreign_gain_split` |
| Price packs are per market and must be ticked on *Price files*; Europe and Gulf are `publish=False` | `/investments/prices/markets`, `issues/6-market-data/6A-price-packs.md` (6A) |
| Statement import is cash only; dividends are entered net ("Enter the amount after any tax withheld"); no share transfer between brokers; average cost only | `lightning/bank_imports.py`, `service.py:530`; lots in `docs/proposals/investment_lots.md` |
| Broker cash counts in Cash you own, and so in Free cash and Safe to spend | `planning/position.py`; sample: 21,016 of 243,692 |

**What this means.** A broker that trades in one currency fits perfectly. A broker that trades US, London and Saudi
shares has to be entered as three accounts today, with "transfers" between them standing in for the broker's own
currency conversions. That is not how the user's statement looks, so they won't reconcile it.

### 3. What brokerages look like to an Egyptian user

| Kind | Examples | Markets | Cash | What the model needs |
|---|---|---|---|---|
| Egyptian broker | THNDR, EFG Hermes, CI Capital, Mubasher Trade… | EGX, Egyptian funds | EGP (a few EGX lines trade in USD) | One pocket, sometimes a USD one |
| Regional broker | Gulf brokers, regional houses with GCC desks | Saudi, UAE, Kuwait, Qatar… | SAR, AED, KWD… | Several pockets, mostly pegged to the dollar |
| Global multi-currency broker | Interactive Brokers, Saxo, Swissquote | Any | Base currency plus a balance in any currency; conversion inside the account; a balance can go negative (margin) | Pockets, conversion inside the account, a guard against negative balances |
| Single-currency platform | eToro-style apps | Many | One cash currency (usually USD); the platform converts on every trade | Settlement currency ≠ listing currency: a conversion is part of each trade |
| Bank funds | NBE, CIB, Banque Misr funds, including dollar funds | Funds | EGP or USD | A fund priced in USD without an exchange |

These examples show the shapes; check each broker's current offer before it goes in the institution list.

### 4. What breaks, or will break, as exchanges are added

1. **A multi-market broker is split into N accounts**, with no broker total and no place for its own conversions.
2. **Currency follows the exchange, which is wrong for:**
   - London: most shares are quoted in pence (GBX), and many UCITS ETFs trade in USD there. `iso.py:40` says
     pence handling isn't built.
   - EGX lines that trade in dollars.
   - Depositary receipts: CIB's GDR trades in London in USD, while COMI trades on EGX in EGP.
3. **Dollar funds can't exist**, because an unlisted fund is forced to EGP.
4. **A trade can't be paid in another currency** ("paid USD, bought a EUR stock"), and neither can a fee billed in
   another currency.
5. **Screens mix currencies without labels:**
   - Holdings table: QQQM shows "Average cost 11,108" (EGP per unit) beside "Price 247" (USD).
   - Holding chart: "Average cost 215" is the EGP cost at today's rate, but the dollars paid were 220.63 per unit.
   - Trades table: price 11,108 (EGP).
   - Prices page: no currency column.
   - Account header: "Balance 114,211" for a USD account.
6. **The Currencies tab leaves out foreign holdings**, so the FX exposure the user most needs isn't shown. This is already
   filed: `technical-bug/2026-10-15-overview-foreign-money-leaves-out-dollar-holdings.md`.
7. **Markets aren't followed automatically:** Mohab holds QQQM, yet *US stocks and ETFs* is unticked.
8. **Some offered exchanges have no FX source.** Nasdaq Iceland (ISK) is in the exchange menu, but CBE and Banque Misr
   don't publish ISK, so a holding there can't be valued.
9. **Three-decimal currencies:** KWD, BHD and OMR use three minor units (ISO 4217), but every cash asset gets 2
   decimals, so Kuwait, Bahrain and Muscat amounts would be rounded or refused. JPY has 0.
10. **Dividends are net only:** yield is understated and the tax withheld abroad is invisible.
11. **Foreign broker cash counts as spendable** (Safe to spend includes the USD sitting at the US broker).

### 5. Principles

1. **One broker, one account on screen**; pockets are detail.
2. **Money never changes currency silently.** Every conversion is a visible event with its rate and its spread against
   the market rate (the *Spread paid* figure already exists on Currencies).
3. **A figure not in EGP always shows its currency**, with "≈ EGP" beside it.
4. **Two lenses for every return:** its own currency and EGP.
5. **Infer from the institution and the ticker;** ask only what can't be inferred.
6. **Keep "one account line, one currency"** in the ledger. It is why everything reconciles.

### 6. The model

#### 6.1 Three ways to do it

| Option | What it is | For | Against | Verdict |
|---|---|---|---|---|
| A. One account per currency (today) | "IBKR USD", "IBKR EUR" as separate accounts | No code | Fragments the broker; no total; conversions look like transfers; lazy users won't do it | Keep only for single-currency brokers |
| B. Many currencies on one account line | Relax the rule: a line's amount is in its asset's currency, not the account's | Purest model, matches IBKR | Touches about 100 uses of `account.currency`, every balance, register, reconciliation and FX rule; high risk to the books | Not now |
| **C. Pockets as child accounts** | Add `accounts.parent_id`. The broker account is the home-currency pocket; each other currency is a child with its own currency. Screens roll children up into the parent | Every ledger rule stays true; conversions inside the broker are the existing Convert between two accounts; reports group by `coalesce(parent_id, id)` | The roll-up must be applied in the sidebar, account page, Accounts list, holdings "Account" column, reconciliation and import | **Build this** |

#### 6.2 Changes to the data

- `accounts.parent_id` (nullable, brokerage only, one level). A pocket inherits the parent's institution and markets,
  and its name is "<broker> · <currency>". Pockets are created on demand ("Add a currency") or when the first trade,
  deposit or import row in that currency needs one (with a one-line confirmation).
- `account_markets(account_id, market)`: which markets the broker trades (EGX, Egyptian funds, US, Gulf, Europe…). It
  scopes the ticker search, sets which price packs to follow and tells the trade form which pocket to use.
- `institutions.csv` gains for brokers: `markets` (default chips), `home_currency` and `cash_model` (`single`, `multi`
  or `auto_fx`). For example: THNDR → EGX + Egyptian funds, EGP, single; Interactive Brokers → US (user adds more),
  USD, multi; an eToro-style platform → many markets, USD, auto_fx. Add the foreign brokers Egyptians use.
- `financial_assets`: `currency` stays but is taken **from the instrument pack per listing** (the pack already has a
  `currency` column, `market_data.md` › The market file), not from `VENUE_CURRENCY`. Add `price_scale` (100 for GBX,
  1,000 for KWF; TradingView's `MINOR` map already knows them). Allow `currency` on unlisted funds.
- `registered_currencies` and cash assets: decimals from ISO 4217 minor units (KWD, BHD and OMR 3; JPY 0).
- Ledger lines: **no change.** Native cost = sum of `amount_e6` in the pocket; EGP cost = sum of `amount_base_e6`.

#### 6.3 New investment events

These fit the one-events-table proposal (`issues/5-investments/5A-one-table-of-investment-events.md` (5A)).

| Event | Posting (pockets are accounts) |
|---|---|
| **Send money to the broker** (EGP bank → USD pocket) | One Convert: CIB −51,600 EGP; IBKR·USD +1,000 USD; implied rate 51.60, spread vs market shown; fee lines in the currency charged |
| **Convert inside the broker** | IBKR·USD −1,087; IBKR·EUR +1,000; optional fee |
| **Buy / sell** | As today, in the pocket of the listing currency |
| **Trade paid in another currency** (auto-FX platform, or the user says so) | Two linked events saved from one form: Convert USD→EUR at the implied rate, then Buy in EUR. The user types "Paid 1,087 USD" and sees "= 1,000 EUR at 1.087" |
| **Dividend with tax withheld** | Gross into Dividends (income); tax withheld into *Investment › Tax withheld*; net lands in the pocket of the dividend's currency. Today's "net only" stays as a shortcut |
| **Broker fee** (custody, data, inactivity) | Out of the pocket it is billed in; category Fees, flagged *investment cost* |
| **Interest on broker cash** | Into the pocket; Investment › Interest |
| **Move shares between brokers** | Units out of one account and into the other at the same cost and original dates; no cash, no gain |
| **Later:** splits, bonus shares, mergers, ticker changes | Existing proposals: `bonus_shares_and_splits.md`, `investment_lots.md` |

A pocket may not go below zero in v1: the error offers "Convert from <other pocket>" inline. Margin is out of scope.

### 7. Workflows, screen by screen

#### 7.1 Set up a brokerage (the lazy path)

1. **Add account → tap the broker's tile.** Type, name and home currency follow from the institution.
2. **"Where do you trade here?"** shows market chips pre-ticked from the institution (THNDR: EGX + funds; IBKR: US).
   A tap adds London, Gulf, Europe.
3. **"What's in it?"** offers two ways:
   - **Import** a positions or activity statement (CSV) and review it like a bank import (§7.6).
   - **Type it:** cash per currency ("USD 1,200", and a pocket appears as a chip), then holdings. The ticker search is
     limited to the chosen markets and shows each listing's currency. Enter units and total paid in the listing
     currency; the EGP cost is computed for the date. One date for all by default; "I bought these on different days"
     opens a date per row.
4. **Done.** The account page shows the total in EGP, a pocket strip ("USD 1,200 · EUR 0 · GBP 0") and the holdings.
   Behind the scenes the app registers the currencies, follows the markets' price packs and fetches FX. The user never
   visits *Price files*.

#### 7.2 Send money to the broker

"Send to <broker>": *From* (CIB, EGP), *Sent* 51,600, *Received* 1,000 USD, optional fee. The app picks the USD pocket
from the received currency, shows "51.60 per USD · market 51.45 · spread 150 EGP", and records one Convert. Linked bank
SMS or import rows are matched instead of creating new ones.

#### 7.3 Buy, sell and dividend: one row each

- **Buy:** ticker (scoped to the broker's markets) → shows the currency and last price → units → total → fees under a
  link → Save. The pocket follows the listing currency. If the pocket is short, the form offers "Convert 87 USD to EUR
  first?" with the rate prefilled.
- **Sell:** same row; the realised gain is shown in the listing currency and in EGP before saving.
- **Dividend:** gross, tax (prefilled from a per-market default the user can change and the app remembers per
  security), net computed. If the broker paid in another currency, show "Paid in" and record the conversion.

#### 7.4 Convert inside the broker

The account page has a *Convert* button between pockets: two amounts, the rate is computed, the market rate is shown.

#### 7.5 See a multi-market broker

Header: name, institution tile, "≈ 186,400 EGP", and today's change. Under it:
- **Pocket strip:** cash per currency with "idle since" when cash has sat untouched for more than 30 days.
- **Holdings:** grouped by market, each price in its own currency, value in EGP, return in both lenses.
- **Activity:** money in and out, trades, dividends and conversions. Monthly revaluation rows are folded into one line
  per month (today they are most of the register).

#### 7.6 Import from the broker

- **Activity CSV:** rows typed as deposit, withdrawal, conversion, buy, sell, dividend, tax, fee or interest, each in its
  currency, then the same row review, chips and bulk bar as the bank import (designs 004). Presets per broker export
  format, starting with Interactive Brokers' activity statement and whatever THNDR and EFG Hermes can export.
- **Positions CSV:** compare units per security and cash per pocket ("Statement 180 COMI · Lightning 180 ✓"). This
  extends *Reconcile* to brokers.

#### 7.7 Move or close

Move shares to another broker (§6.3). Close a pocket when it is empty. Close the broker when every pocket is zero.

### 8. Prices, FX and market calendars

- **Follow automatically** every market a broker trades or a holding sits on. *Price files* becomes a status list
  ("US prices up to 2026-10-14 ✓ · Gulf: no shared file yet, using your typed prices").
- **Per-listing currency and scale:** convert GBX to GBP (÷100) and KWF to KWD (÷1,000) once, at import, so every screen
  shows the ISO currency.
- **FX coverage gate:** offer an exchange only when its currency has an FX source, or ask for a manual rate on first use.
  ISK fails today.
- **Dates:** the month-end close is the last close on or before the month end for each listing (as today). Gulf
  markets that trade Sunday to Thursday and US and European markets that trade Monday to Friday close on different days,
  and FX rate dates differ again. Show "as of <date>" per market in the holdings table, not one date for the whole page.
- **Pegs:** SAR, AED, QAR, BHD and OMR are pegged to the US dollar, and KWD to a basket. Use the pegs to group the
  currency view and to sanity-check FX data: a pegged rate that moves away from the dollar's is a data error.

### 9. The analysis

#### 9.1 Investments home

The hero is Portfolio value in EGP, with "≈ 6,830 USD" under it and the period change. A view switch below it offers:
**Class · Account · Currency · Market · Security**. Each view is the same table grouped differently. That replaces the
current single grouping and the savings-rate waffle at the top.

#### 9.2 Views

| View | Shows | Why a user cares |
|---|---|---|
| **By account** | Each broker: total, pockets, holdings count, return since start, fees and spread paid this year | "Is THNDR or IBKR working better for me?" |
| **By currency** | EGP, USD and dollar-pegged Gulf currencies, EUR, GBP, other. Covers cash, holdings, certificates and gold, and replaces today's foreign-money-only Currencies tab | "How much of my money is protected if the pound falls?" The most important chart for this audience |
| **By market** | EG, US, Gulf, Europe; home bias | "Am I all-in on Egypt?" |
| **By security** | One row per security even when held at two brokers, with the breakdown | Concentration across brokers |
| **By class** (today) | Stocks, funds, gold, certificates | Allocation and targets |

#### 9.3 Returns in two lenses

- **Per holding and per portfolio, for the period and since the start:** price in its own currency + FX + income (net
  of tax) − fees + realised gain, as a waterfall in EGP. A toggle shows the same in the listing currency. Today the split
  exists only for unrealised gain (`foreign_gain_split`); extend it to realised gain and income.
- **What the pound did:** "Of your +44,559, 18,000 came from the pound weakening." Compare against "kept in a 22%
  certificate" (Upcoming project #1, risk-free benchmark) and "kept in dollar cash". (These figures illustrate the
  shape; they are not computed from the sample.)
- **Holding page:** average cost in the listing currency (220.63, not 215) with EGP beside it, trades with native price
  and EGP amount, and the FX rate at purchase vs now.

#### 9.4 Income, costs and idle cash

- **Income:** dividends and interest by month and currency, gross, tax and net, and yield on cost.
- **Costs:** commissions, FX spread and broker fees per broker per year ("What THNDR cost you in 2026"). Most apps hide
  this. Lightning already measures spread.
- **Idle cash:** a pocket over a threshold for more than 30 days goes to Needs you ("1,200 USD idle at IBKR since August").

#### 9.5 Targets

Today targets are by class. Add optional targets by currency ("at least 30% outside EGP") and by market. The Planner's
suggested split then respects them.

### 10. How it wires into the rest of the app

| Place | Change |
|---|---|
| Overview | Net worth unchanged (EGP). Add one line, "Not in pounds: 22%", opening Investments › By currency. The Currencies sub-tab becomes that view, so there is one page instead of two |
| Cash planning | Broker pockets and foreign cash are out of Spendable by default (per-account switch; companion report §3.4.5) |
| Health | Optional "Share outside EGP" with a limit; emergency fund leaves out broker cash |
| Zakat | Holdings and pockets valued at the zakat day's rates; nisab stays in EGP |
| Needs you | Missing FX for a held currency, idle pocket, units that don't match the statement, dividend tax unknown |
| Search (Ctrl-K) | "buy 10 aapl" goes to the broker that trades the US market, or asks which one when two do |
| Import | Broker activity and positions presets |
| Phone | One card per broker with pocket chips; the same one-row trade form |
| Sample year and Mohab | Give Mohab a multi-currency broker so every screen is exercised (§12) |

### 11. Edge cases, decided up front

| Case | Decision |
|---|---|
| Same company on two exchanges (COMI on EGX, the CIB GDR in London) | Two listings and two securities; an optional "same company" link later for the By security view |
| Pence, fils | Scaled at import (§8) |
| EGX lines in USD | Listing currency USD; needs a USD pocket at an Egyptian broker |
| Fractional shares | `quantity_decimals` per listing (US brokers allow fractions) |
| A pocket would go negative | Refused in v1 with an inline Convert; margin later |
| Holdings entered for a date before any FX rate | Ask the rate, or the EGP cost, on that row |
| Held for others in a foreign pocket | Works as today: custody is per owner, account and asset, and pockets are accounts |
| Ticker change or delisting | `market_key` stays; the name and ticker update (already done for renames) |
| Three-decimal currencies | ISO minor units (§6.2) |
| Profile currency other than EGP (diaspora) | Out of scope, but keep "EGP" out of screen code; read the profile currency |

### 12. Build plan

Each phase ships on its own and is proved by Mohab steps in `tests/test_mohab_year.py`.

| Phase | Scope | Proof (new Mohab steps) |
|---|---|---|
| **0. Honest display** (no model change) | Currency on every non-EGP figure; native average cost; Currencies includes holdings; follow held markets; exchange names without MIC codes; spendable switch for broker cash | The QQQM row shows "220.63 USD"; Currencies shows QQQM; *US stocks* is followed; Safe to spend drops by 21,016 when the switch is off |
| **1. Listings** | Currency from the pack per listing; GBX/KWF scale; USD funds; ISO decimals; FX coverage gate | Mohab buys a London ETF that trades in USD and a GBX-quoted share; both value correctly in EGP |
| **2. Pockets** | `parent_id`; account page with pocket strip; trade form picks the pocket; Convert inside the broker; sidebar and reports roll up; "merge into a broker" for today's separate USD account | Mohab's Dollar brokerage becomes "IBKR" with USD and EUR pockets; converts 500 USD to EUR; buys on Xetra; net worth moves only by the spread and fee |
| **3. Events** | Dividend gross/tax/net; broker fees; interest on cash; move shares between brokers | A 4.00 USD dividend with 0.60 tax: Dividends +4.00, Tax withheld −0.60, pocket +3.40 |
| **4. Broker import** | Activity and positions CSV presets; unit reconciliation | Import of an IBKR activity CSV reproduces phase 2's ledger exactly; positions check passes |
| **5. Analysis** | Five views; two-lens returns; what the pound did; costs; idle cash; targets by currency and market | Every view's total equals Portfolio value; price + FX + income − fees + realised = Net gain (number-audit) |
| **6. Lots and corporate actions** | Existing proposals | As in those proposals |

Phase 0 is small and fixes what users already see. Phases 1 and 2 are the structural core and should be built before
more exchanges are switched on. Every new Gulf or European market without them adds holdings that can't be entered
the way the broker reports them.

### 13. Questions for the owner

1. **Pockets in the sidebar:** one row per broker (pockets only on the account page), or expandable rows?
2. **Trades paid in another currency:** record them as two linked events (Convert, then Buy). Agreed?
3. **Dividend tax:** prefill a default per market that the user can change, or always ask?
4. **Currency view:** group the Gulf currencies with the US dollar (they are pegged), or list each one?
5. **Dollar lens:** should Investments offer "show in USD" for users who think in dollars?
6. **Institution list:** which foreign brokers go in first (Interactive Brokers, eToro, Saxo, Swissquote…)? And may the
   list carry each broker's default markets?
7. **Margin:** refuse negative pockets for now?
8. **Order:** should Phases 0-2 come before switching on the Europe and Gulf price packs (today `publish=False`)?

## Fix

Built 2026-10-16 (merged to main):

- **Phase 0, complete:**
  - A foreign holding's price, average cost (220.63 USD, not 215) and trade prices are shown in its own currency.
  - A USD account's header reads in USD, with ≈ EGP beside it.
  - Prices show their currency.
  - Foreign money counts foreign investments.
  - Held markets are followed automatically.
  - Exchange names appear without MIC codes.
  - **Kept apart** (`0065_account_spendable.sql`): brokerage and foreign cash leave Free cash and Safe to spend, with a per-account override.
- **Phase 1, partly done:**
  - A listing can trade in another currency than its exchange (`create_investment(currency=)`, catalogue currency used).
  - USD funds are possible.
  - Exchanges without an FX source are not offered (`offered_venues`, ISK).
  - KWD, BHD, OMR and JOD keep 3 decimals.
- **Institutions:** 11 brokers now carry `markets` and `home_currency`, as data only.

**Open:**
- Phase 1: per-listing price scale. GBX→GBP happens at the TradingView source, and the pack catalogue for London and the Gulf is not in the picker yet.
- Phases 2-6: pockets, events, broker import, analysis views, lots.
- §13 questions for the owner.

Round 2, 2026-10-16. The owner answered §13: one row per broker; convert then buy; tax optional (net is the default); list each currency; a USD lens; the most popular brokers with their markets; no margin or short selling. On Q8 the decision was ours: these phases first, Europe and Gulf packs later.

- **Phase 2, pockets (`0067_broker_pockets.sql`, `accounts.parent_id`):**
  - A foreign listing is held in its currency's pocket, made on demand.
  - *Paid in another currency* converts, then buys.
  - The sidebar and Accounts show one row per broker. Its page shows cash by currency and every holding, with ⋯ › Add a currency.
- **Phase 3, events:** optional dividend tax (`0066_investment_tax_category.sql`), broker fee, interest on broker cash, and moving shares between brokers.
- **Phase 5, views:** By class, account, currency, market and security. Also a By currency card, a USD lens, and the share of the gain that came from exchange rates.
- **Brokers:** added Al Rajhi Capital, SNB Capital, Derayah, Sahm Capital, Emirates NBD Securities, Charles Schwab International and Trading 212. Interactive Brokers now lists the Gulf.

**Still open:**
- Phase 4: import of broker statements and positions.
- Merging today's separate *Dollar brokerage* into a broker as a pocket.
- In the USD lens, the allocation card and brokerage cash stay in EGP.
- Phase 6: lots and corporate actions.
- Turning on the Europe and Gulf packs once their sources are licensed.

Owner direction (ticket 107, 2026-10-16): this design's pockets read as tabs: one tab per currency pocket of a brokerage, each limited to markets that trade in that pocket's currency, plus a main tab that adds them all up in EGP. Agree with section 1; next step is to settle the pocket list per broker and the tab layout before any code.
