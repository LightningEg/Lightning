# Investment workflow audit: PC actions, convenience and valuation

Date: 2026-11-14 · Author/reviewer: Codex
Repository: app · Reviewed commit: 603d7fe34c20e66121757b2419d68d55a69ca0c0
Code: r37
Pillar: Own

## Assessment

The PC workflow has a useful foundation, but **it does not yet have the right actions for every investment type, and valuation is not consistently reliable across all paths**. The main demo portfolio adds up; several less-common but ordinary workflows produce wrong values or quantities. Passing the existing suite does not cover these newly reproduced cases.

The most urgent work is currency correctness and the Prices editor, followed by amount-only sales. Then make the holding page choose actions by investment type. A new investing feature is less useful than making the existing paths agree.

## Owner decisions and scope

- Owner, 2026-11-14: main figure means **current market/estimated value**, with **sale proceeds shown separately**.
- Owner, 2026-11-14: **PC experience is the priority for investments**. Phone evidence is supplementary.
- Existing decisions remain: bonds, treasury bills, business stakes and pension/insurance holdings use Other with typed valuations; property instalments count amounts paid and keep future payments in the forecast. See r30 dated follow-ups. This audit does not reopen those product choices.
- Audit only. No application fixes, migrations, real-money entries, market orders or deployments.

## What was exercised

Updated the supplied stale workspace to current main, version 2.2.1. Ran the disposable demo on localhost, traversed its desktop pages in Chromium at 1280 × 900 and targeted 1366 × 768, clicked a stock holding → Buy more → recorded a purchase, opened the certificate Buy more dead end, and tried gold's dividend action. Inspected add doors, prices, planner, targets, broker register, gold account, certificate account and holding pages. All saved data was synthetic.

Used isolated FastAPI/service fixtures for foreign-currency trades, amount-only sales, two-broker price changes, physical-item valuation, certificate price overrides, malformed input and duplicate submission. Followed rendered controls through route/service/ledger code. Ran a bounded 600-page GET crawl and existing financial/user-year tests; full-suite result is recorded below. Supplementary phone checks use the actual phone renderer, not a desktop page narrowed to phone width.

Evidence directory contains reproducible script/output and selected desktop screenshots. A source finding or recommendation is distinguished from a browser reproduction below.

## Reproduced financial findings

| ID | Severity | Expected | Observed | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | High | A monetary field's currency matches the posting | USD buy form says EGP. Entering 100 debits USD 100 and records EGP 5,000 at FX 50. | [BT-12AM](../BT-12AM-foreign-trade-currency.md) |
| F2 | High | A freshly bought unchanged USD holding has 0% return in its lot detail | Headline value/cost EGP 5,000; Each purchase values it at 100 and shows −98%. Native price is compared with base-currency cost. | [BT-12AN](../BT-12AN-foreign-lot-returns.md) |
| F3 | High | Sell by net amount 100, fee 10, price 10 removes 11 units | Removes 9 units while crediting 100 cash. The buy fee formula is reused for sales. | [BT-12AO](../BT-12AO-amount-sale-fees.md) |
| F4 | High | A total-value edit has an explicit, consistent scope across accounts | 91 + 50 units; total value entered 1,500. Only 50 units determine price; portfolio becomes 4,230. Prices also shows only the last account's held quantity. | [BT-12AP](../BT-12AP-price-update-scope.md) |
| F5 | High | Saving a named gold item's estimate changes its valuation, or refuses the unsupported route | Prices accepts 60,000 for an item worth 50,000; value remains 50,000. Ordinary price writes are ignored by its item-specific valuer. | [BT-12AP](../BT-12AP-price-update-scope.md) |
| F6 | High | Certificate value follows its contract and explicit accrual/redemption rules | Prices hides per-unit editing but allows Total value: principal 1,000 becomes value 2,000 and an invented 1,000 gain. | [BT-12AQ](../BT-12AQ-certificate-price-override.md) |

The same gold failure was also reproduced through visible PC clicks: enter 45,000, click Save prices, receive “Saved 1 price input; reevaluation catch-up completed,” and find the holding still at 37,200 ([PC evidence](evidence/pc-price.txt)).

Exact requests, input dates and numerical results: [reproduce.py](evidence/reproduce.py), [reproduce.txt](evidence/reproduce.txt). Dates in these fixtures are explicitly fixed to 14 November 2026. These six findings are grouped into five follow-up items; no repair is claimed.

## Does each type have the right buttons?

| Investment type | What works now | Missing, misleading or inconvenient | Recommended PC actions |
| --- | --- | --- | --- |
| Stocks | Buy/Sell, cash dividend, split/bonus, return of capital; broker register has fee, cash interest and move. Buy more prefilled the right account and asset and saved successfully. | Generic form and broker register expose different capabilities. Moving, tax detail and cash fees are distant from the holding. Switching Buy to Sell loses the chosen asset. Foreign amount labels and lot returns are wrong. | Buy more, Sell; Income, corporate action and Move under More. Keep account/asset/currency prefilled; show cash impact before saving. |
| Funds | Shared buy/sell/dividend model; broker register can derive units from an amount. | Main Buy form requires Units even when the register allows amount-only entry. Amount-only sale with fees is incorrect. A money-market fund should not require discovering another page to enter a cash amount. | Add money / Withdraw (or Buy/Sell with amount-first entry), Income, Update NAV, transfer where supported. Keep advanced actions secondary. |
| Certificates | Separate CD purchase/owned-before-tracking, receipt, redemption, term and forecast workflows; unlock/maturity attention exists. | Holding page still offers stock Buy more/Sell/Dividend: Buy more opens with no eligible CD account; POSTs are refused. Rate, next payout and maturity are absent from this page. General Prices can override value. At-maturity accrued interest remains planned, not built. | Buy another certificate, Record bank payout, Redeem when eligible, Edit terms. Lead with principal, accrued estimate where applicable, rate, next payout, unlock and maturity. Existing [IV-12J](../IV-12J-certificates-read-as-certificates.md), not a duplicate redesign. |
| Gold bars, coins, jewellery | One-step Gold door, piece count/weight/karat, purchase/sale, workmanship and manual item estimate on the gold account. Reference-price valuation works in baseline tests. | Holding page offers Record a dividend; actual attempt is refused. General Update price leads to the non-working override path. Generic buy omits item-specific workmanship context. | Buy/record another piece, Sell pieces, Update estimated value, Edit item/weight details. Show grams, karat, source/date and separate likely sale proceeds. No dividend action. |
| Property | Own account page has dated estimates, purchase details, rent/cost recording and instalments. Existing tests cover this integration. | The Property door opens a generic Other-account setup; subsequent account, purchase details and valuation are separate concepts. No dedicated sale/closing settlement action was found in the property controls. | Update estimate, Record rent/cost, Pay next instalment; guided sale/close flow if the owner later chooses it. Preserve the existing paid-so-far valuation rule for off-plan contracts. |
| Private stakes / collectibles / other | Manual assets and valuations; general investment actions available. | Something else creates an asset definition without guiding through where it is held and how much is already owned. Generic dividend recording requires a brokerage account, which may not fit a private stake. | Add existing stake, Add/reduce capital, Distribution to a chosen cash account, Update estimate. Treat this as a later UX choice within the approved Other model. |

The action list should depend on **type and state**, not simply whether a holding exists: no gold dividends, no stock sells for CDs, no sale larger than owned units, no redemption before unlock, and an explicit way to inspect a fully sold holding's history.

## PC convenience and configuration findings

1. **Two entry experiences disagree.** The broker register has type-ahead catalogue search, amount-or-units entry, dividend withholding, fee/interest/move. The prominent Add investment → Stock or fund path sends users to a longer general form with a different feature set. Recommend one shared investment-entry model with contextual fields; keep the register as another entry point to it. Source: `partials/investment_entry.html`, `investments/form.html`, `workflows/investment_entry.py`.
2. **Context gets lost on an action change.** Open Buy for COMI in THNDR, then click Sell: account remains, asset selection clears. Reproduced in [pc-actions.txt](evidence/pc-actions.txt). Action links preserve `account` but omit `asset`. Preserve both, and preserve drafts when adding a new instrument.
3. **The portfolio answers value before it offers work.** Positive: main value, cost, gain, allocation and sale estimate are together; a clear Add investment exists. At 1366 × 768, the holdings list is below the fold, after the explanation block. For a desktop user managing investments, move a compact holdings/action table ahead of expanded analysis, or make the explanation collapsible. Evidence: [desktop overview](evidence/desktop-investments.png), [PC fold](evidence/pc-1366-fold.png). This is a recommendation, not a financial defect.
4. **Certificate selection assumes the first bank.** The Certificate door redirects to the first active CD portfolio if any exists. With multiple banks it provides no bank choice at that door. Confirmed in `_first_cd_portfolio` / `add_certificate`, not a multi-bank browser session. Offer bank/portfolio selection, with the current one preselected when coming from a certificate.
5. **Financial terms remain demanding.** Units, allocation bucket, horizon, risk-free rate, return of capital and bonus/split are all supported, but exposed close to ordinary entry. Keep units where they matter; use pieces/grams for gold and principal/interest for CDs. Put advanced corporate actions and benchmarking behind More, while showing straightforward cash impact and current holding beside the form.
6. **Price freshness needs a stronger contract.** The app has source/date and stale-price machinery; price files, trades, manual entries and cost fallback do not all mean market value. A correct multiplication is not evidence the quote equals an executable sale price. Show Market price / Estimated / At cost / Missing beside the figure, with the quote date and FX date, and a direct relevant update action.
7. **Sale proceeds are already separated, but remain estimates.** Class sale factors and certificate lockups influence the figure. The fallback is 95% for most investment classes and 0% for real estate until configured (`investments/domain.py`); this is a liquidity assumption, not calculated actual selling fees or a market quote. The demo's 177,903 market/estimated portfolio shows 74,007 after-sale estimate because a 100,000 certificate is locked and other sale factors apply. The current “Locked certificate … not counted until” wording should explicitly say “excluded from sale proceeds”: the certificate is correctly still included in portfolio value. Label exclusion and assumptions explicitly. Do not call this an available bank quote or cash balance.
8. **Minor selectable-reference leak.** The clean fixture's general investment picker still listed an 18K gold price reference despite filtering `REF:` codes. It is not a user holding. Rejecting a reference is tested; filtering should use its semantic role, not only code prefixes. The fixture text is preserved in the reproduction output.

9. **Per-unit prices lose useful decimals.** COMI's holding page shows 150 shares, value 12,975 and “Price 87”; the actual quote is 86.50 (150 × 86.50 = 12,975). The valuation is right but cannot be recomputed from that rounded displayed price. Keep cents on unit prices and average costs; whole EGP is suitable for large totals. Desktop rendered text: [COMI page](evidence/comi-holding.txt).

Nonfinancial suggestions are recorded in [INBOX.md](../../INBOX.md); existing certificate and local-gold-source work remains linked rather than duplicated.

## What is accurate in the paths checked?

Before the browser's extra stock purchase, the demo at 14 November 2026 showed:

| Check | Expected | Observed | Result |
| --- | --- | --- | --- |
| Portfolio components | 100,000 CD + 57,195 gold + 17,675 stocks + 3,033 fund | 177,903 | Pass |
| Unrealized gain | 177,903 − 167,050 cost | 10,853 | Pass |
| Lifetime total gain in holdings | 10,853 + 3,666.67 paid certificate interest, rounded | 14,519 | Pass |
| November result components | 5,673 price change + 0 FX + 0 sale gain + 1,833.33 income, rounded | 7,506 | Pass |
| Broker balance | 17,675 stocks + 3,033 fund + 400 brokerage cash | 21,108 | Pass |
| Gold account vs portfolio gold | Same two item values, 37,200 + 19,995 | 57,195 in both | Pass |
| Malformed/invalid trade input | No new transaction on rejection | All 16 boundary probes rejected, zero writes | Pass |
| Same token submitted twice | One transaction | Two redirects, one new transaction | Pass |
| Synthetic internal ledger movements | Each transaction nets to zero in base currency | Zero unbalanced transactions | Pass |

The actual desktop purchase was reconciled on a temporary copy of the demo database ([move check](evidence/move-check.txt)): buying one COMI share for 100 EGP reduced broker cash by 100, increased units by one, increased cost by 100 and market value by 86.50. Net worth and the period result both fell by 13.50, exactly the gap to the existing 86.50 quote. Before the purchase, net worth was 250,762.36: account value 260,762.36 less 10,000 held for someone else. The difference is intentional, not a mismatch.

The portfolio and account totals can reconcile **and still be wrong** after a bad price input: they share the same valuation source. F4 and F6 illustrate why independent expected-value checks are necessary. F2 illustrates the reverse: the headline can be correct while a supporting table is wrong.

Gold value is an estimate based on dated karat references, not a verified local shop bid. Property value is a dated user estimate. Cost/last-trade fallback is not a current quote. At-maturity certificate accrual is still an existing gap (IV-12J3); do not claim full economic valuation correctness until it is implemented and reconciled.

## Validation and limits

- 263 targeted investment, valuation, certificate, physical-item, property, FX, source-order and Mohab year tests: completed successfully (exit 0); collection counts in [targeted-collection.txt](evidence/targeted-collection.txt).
- GET crawl: 600 pages, no non-200/title/broken-text findings. Bounded crawl, not proof every route was visited.
- Desktop browser: 17 selected paths at 1280 px returned 200 with no recorded JavaScript errors or document overflow; targeted real interactions above at desktop widths. A successful GET does not prove its forms are appropriate (CD is the counterexample).
- Supplementary actual-phone renderer check at 360/320 px: holdings sheet 5 overflow on Investments; other selected pages produced no reported overflow. Not prioritized over PC.
- Documentation check: only the app/website guideline mirror test failed; this audit changed neither guideline. The sibling website checkout is older than updated app main. Item schema check passes with existing/cap warnings.
- Full suite (`pytest -q -n 4 --dist loadfile`) completed, exit 1: 3 failures, 13 browser setup errors and 11 skips. [Summary](evidence/full-suite-summary.txt). Browser errors were 5-second setup/navigation timeouts; failures were packaging distribution discovery (Jinja2), the older website guideline copies, and the report-code check running during the reservation/folder transition. Serial recheck: all 13 browser cases and the final report-code check passed (14 passes); packaging-distribution discovery still failed. The website mirror failure remains unchanged. [Recheck log](evidence/failure-recheck.txt). These are separate from the six financial reproductions; no clean full-suite result is claimed.
- Live external quote accuracy and source availability, real bank/broker statements, native Windows WebView2 packaging, physical-device behavior and exhaustive Arabic/RTL were not independently verified. Shared-desktop tools were unavailable; Chromium/Playwright was used. No personal portfolio was supplied or opened.
- Board CLI could not read `api.github.com` in the environment; connected GitHub lookup and local plan files supplied existing-work context. GitHub issue creation was interrupted, so the five follow-up item files are prepared with the report; no issue numbers are claimed. No other actor's implementation files were changed.

## Recommended order

1. Fix F1–F6 with regression cases from this report: currency labels and lot FX, amount-only sale fees, multi-account/physical-item price handling, and contractual certificate price protection.
2. Deliver the existing certificate page work (IV-12J1/3) and type-appropriate gold actions.
3. Unify the PC transaction entry experience and keep asset/account context. Put holdings and common actions ahead of expanded analysis.
4. Improve quote provenance, bank selection and guided Other/property journeys; assess the phone overflow later.

## Dated follow-ups

No fixes applied in this audit. Owner's value definition and PC priority are recorded above.
