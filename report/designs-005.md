# Designs 005: the owner's second walk-through (15 tickets)

Follows designs 004 and builds on its branches (header T10, `.form-grid` T11, institution tiles T7, field wells T2).
Every ticket is approved to build except where marked **Proposal**. Delete this file with the batch.

Read code by grep and line ranges, never whole files. Guideline via `python tools/guideline.py A08`.
New visible strings get Arabic in `lightning/ui/i18n.py`. Phone (Part C) keeps one column.
Financial changes (U7, U11) follow `skills/number-audit/SKILL.md` before and after.

## Branches: stacked, in this order

The first starts from the **last branch of designs 004** (`claude/import-same-day-order`); each next one from the previous.

| # | Branch | Tickets |
|---|---|---|
| 1 | `claude/page-jump-on-hover` | U1, U14 |
| 2 | `claude/register-bulk-edit` | U2 |
| 3 | `claude/account-actions` | U5, U6 |
| 4 | `claude/account-composition-visual` | U4 |
| 5 | `claude/quiet-pickers` | U8, U9 |
| 6 | `claude/investment-entry` | U3, U7 |
| 7 | `claude/markets-setting` | U10, U11 (part built, part proposal) |
| 8 | `claude/salary-and-recurring-forms` | U12, U13 |
| 9 | `claude/health-thresholds` | U15 |

---

## U1 · Page jump: bottom right, only when wanted

- `lightning/ui/static/style.css` ~line 3259 moves the button to the **left** on PC (`@media (min-width:901px) { .page-jump { right:auto; left:20px } }`): that is why it sits over the sidebar. Delete that rule; it stays bottom right (RTL: bottom left, via the RTL build).
- Behaviour (`app.js` ~line 255): hidden by default. It fades in (150 ms) when the pointer comes within ~140px of the bottom-right corner, or while the page is being scrolled; it fades out 1.5 s after the pointer leaves / scrolling stops. Never shown when the page does not scroll. Keyboard focus shows it. Touch (phone): show while scrolling, fade 1.5 s after. Respect reduced motion (no fade, just show/hide).
- Guideline: one sentence in A10 or A15 describing it (it is not described today; check with `grep -n "page-jump\|end of page" guideline/app.html`).
- Test: no `.page-jump` rule sets `left:` for PC; the JS has the proximity handler (string test is enough), plus a Playwright check if browser tests exist.

## U14 · Loading on the PC

- A10.6: "A small Muted square that turns … a slow page shows the square in a note at the bottom right." The PC's `.busy-toast` (`style.css` ~2913) sits **top right** with an **Azure** square (~2910). The owner says the phone's works well.
- Open the same slow action on the phone frame and the PC (Playwright, both widths) and compare. Make the PC match the phone and A10.6: Muted square, note at the bottom right (above the page-jump button, which hides while the note shows), shows after 300 ms, ends with what happened. If the PC never shows anything on page navigation (WebView2 has no browser spinner), make link navigation that takes > 300 ms show the note too, as the phone does.
- Test: CSS: `.busy-square` background is the Muted token; `.busy-toast` is anchored bottom right.

## U2 · Register: edit many rows at once

Today: ticking rows works, but editing a row opens `?edit=` (a page load) and saves that row only; the selection is lost.
- Keep the selection across the edit load (sessionStorage keyed by page URL; restore ticks on load; clear after a save or Escape).
- When the user presses Enter / Save on the edited row **and two or more rows are ticked (including or besides this one)**, show the app's dialog (A10.5, never the browser's):
  "Change 5 selected rows?" · buttons **Only this row** · **All 5 rows** · Escape = cancel.
- "All" posts to a new `POST /transactions/bulk-edit` with `txn_ids` and **only the fields the user changed** in the edited row (compare to the row's original values held in `data-` attributes): Counterparty (including choosing your account = make it a transfer only if every row allows it; otherwise skip those rows), Category, Notes, Held for, Date. Amount is never applied to many rows (say so in the dialog's line when amount changed: "The amount changes on this row only.").
- Service: `TransactionService.bulk_update(ids, changes)` in `lightning/transactions/service.py`, one DB transaction, reusing the single-row edit path per row; rows that cannot take a change (investment rows, splits, opening balances) are skipped and counted, like `set_category` (`routes/transactions.py:403`). Flash: "Changed 4 rows. 1 left as it was: investment rows keep their own counterparty." Keep `/transactions/bulk-category` working (the selection bar's own control) or fold it into bulk-edit; one code path either way.
- Tests: bulk-edit changes category + notes on three rows and leaves amounts; a skipped investment row is counted; only changed fields are applied.

## U5 · "Money actions": one button, only where cash moves

Decision (owner asked Claude to think it through):
| Account type | Money actions menu | Where the rest goes |
|---|---|---|
| Cash, Bank | **Convert currency**, **Change ownership**, **Bought in instalments** | ⋯ |
| Brokerage | none. **Change ownership** stays in ⋯ (a brokerage can hold cash or units for someone else). **Convert** appears in ⋯ only once the account trades in a market of another currency (U11). | ⋯ |
| CDs, Gam'eya, Gold and other things, Other | none of the three | ⋯ |
- In the topbar (`register.html` `top_actions`, and the phone's `phone/register.html:15`): for Cash and Bank, **Money actions** (a menu pill, A10.1 Secondary) is the page's one Secondary; Import statement moves into ⋯. Other types keep designs 004's "Import statement" as the Secondary.
- ⋯ holds: Import statement (where not the Secondary), Adjust balance (U6), Deleted transactions, Edit account, Deactivate.
- Test: a Bank page has a Money actions menu with exactly those three; a Brokerage, CD and physical page have none and no Convert/instalments link.

## U6 · "Check against bank" → "Adjust balance"

- It sets an account to a balance you know on a date and records the difference. Rename everywhere (`register.html:62`, `phone/register.html:15`, the reconcile page's title and button, i18n, Glossary): menu item **Adjust balance**; page title **Adjust balance**; line under: the account and the date. Keep the URL `/accounts/{id}/reconcile`.
- "For everything": offer it on every account type that holds cash (Cash, Bank, Brokerage cash, Gam'eya); for CDs and physical items, the menu says **Update value** and opens their existing valuation/reevaluation page instead. Check `routes/accounts.py:393` for type restrictions and widen to those types.
- Glossary: one entry "Adjust balance". Test: the label "Check against bank" is gone from templates; a brokerage page offers Adjust balance.

## U4 · Account page: composition as a visual, not a table

The "By asset class" table (screenshot: one row "Brokerage Cash 113,524.70 / 100.00% of total / 113,524.70 / 0.00 …") repeats the header's Balance.
- Replace it (`register.html` ~line 88 table) with one Support card **"What's in it"** (A07):
  - one 100% horizontal stacked bar by asset class in A04 colours, then up to four legend rows (A16: four, then Other), each "class · amount · share", whole EGP;
  - when anything is held for others, a second thin bar below: What you own (Azure) vs Held for others (Neutral), with the two amounts;
  - when there is one class and nothing held for others, the card is not shown at all (the header already says it).
- Header (designs 004 T10) keeps Balance and, when different, What you own. Do not repeat them in the card.
- A12 chart rules apply (labels beside marks, no legend boxes far from data). Phone: same card, full width.
- Test: brokerage with one class and no custody → no card; with two classes → a bar with two segments and legend rows; with custody → the owned/held bar.

## U8 · Quiet pickers and fewer words on screen

- **Field jumps** (screenshot 5): the investment picker's results render inside the form row, so the label row shifts. All picker result lists (investment, counterparty, category, institution, currency) become an absolutely positioned popover under the field (z-index above cards, max-height ~320px, scroll inside), never pushing layout. One shared CSS class; grep `-results` classes in `style.css`/`app.js`.
- **One line per result**: name, then the ticker and the exchange in Muted: `Commercial International Bank · COMI · EGX`. Drop the type word ("Stock", "Fund") — the ticker says enough. A fund with no ticker shows its manager in Muted. Long names truncate with an ellipsis, full name in the title attribute. Popover min-width 360px even when the field is narrower.
- **Fewer words** (the owner: "only what is critical"): remove help lines that restate the label or the obvious, starting with the investment form ("Choose Buy, Sell, or Dividend. Units are always entered as a positive quantity.", "Leave fees at 0 when there were none.", "Enter the number of units bought…") and the picker's "Choose an instrument from the results." (show it only as the error after a failed save). Then sweep the main entry forms (account, transaction popup, recurring item, salary setup) for the same; keep a hint only when a user would otherwise get it wrong. Write the rule into A14 Words: "Help text only where a mistake is likely; never under every field."
- Test: the investment form has none of the three removed sentences; result rows contain the exchange code and not "Stock ·".

## U9 · Same ticker on two exchanges

- Instruments are keyed by ticker + exchange (MIC). Show the exchange's short name (EGX, NYSE, Nasdaq, Tadawul, DFM, ADX, QSE, Boursa Kuwait, Bahrain, MSX, LSE, Xetra, Euronext…) after the ticker everywhere a holding is named (picker, holdings rows, transaction rows). Add a MIC → short name map next to the packs (`lightning/market/packs.py` venues).
- Check the catalogue key: if two catalogue rows share a ticker on different MICs, both must be pickable and stay distinct holdings. Test it with a fixture row.

## U3 + U7 · Investment entry: a clean form and fees kept apart from the price

**Fees, the rule (owner decision, this batch):** the price of what you bought is never muddied by fees.
- A buy records **Amount = units × price** (the holding's cost) and **Fees** separately. Cash out = Amount + Fees. A sell: cash in = Amount − Fees.
- Fees are an expense in **Fees & Charges › Investment fees** (create the L2 under the scope the account belongs to, by migration; never edit an old migration). Average cost and price per unit exclude fees.
- Returns stay honest: Investments reports show **Fees paid** as its own figure, and **Net gain** = price gain + sale gains + distributions − fees paid. Update Architecture › Position and reporting contract (line ~160 says "basis … fees included"; change it) and the Glossary.
- Same rule for physical items (a gold ring): the item's acquisition cost is what the item cost; extras (cleaning, tips, delivery) go in Fees as an expense, never in the ring's cost. Update `acquisition_cost` wording in Architecture (~line 133).
- Existing data: first read how fees are stored (`lightning/investments/service.py` `_trade_lines` ~line 479). If the fee is already its own ledger line, switch cost/basis to exclude it for all trades and record in the commit which figures moved (Mohab's, the samples). If the fee is folded into the asset line, apply the rule to new trades only and file a report for migrating old ones. Run number-audit before and after; Mohab must pass (update its expectations only where the fee rule changes them, and say so in the changelog).
- The "Fees inside the amount / Add fees on top instead" choice is removed (`fees_included` stays in the service for imports, defaulting to the new rule for the form).

**The form** (`lightning/ui/templates/partials/investment_entry.html`, screenshots 2 and 5): today the Type is three pills with coloured text (Sell rose, Dividend azure: a colour off its meaning, A16), fields have uneven widths, labels wrap ("Fees (inside the amount)"), and it is an Entry card with prose.
- Entry card (A07), header "Add investment transaction", no line under it.
- Row 1: **segment** Buy · Sell · Dividend (A10.2, chosen in Nile, no tone colours), Date, Investment (wide, the quiet picker from U8).
- Row 2 (`.form-grid`): Units · Price per unit · Amount · Fees. Typing two of Units/Price/Amount fills the third (as today). Dividend shows only Amount and Fees (A10.1: only that kind's fields show).
- Under row 2, one live Muted line: "You pay 10,250 EGP · 10,000 for 100 units at 100.00 + 250 fees" (sell: "You receive …"). Computed by the server's preview endpoint if one exists, else client-side arithmetic for display only (the posted amounts are recomputed in Python).
- Row 3: Held for (type-and-pick, blank = you; replaces the "Held for someone else" checkbox), Notes, and the one primary **Add** button at the end. "Add an existing holding" stays as a quiet link.
- Test: the form has a segment with no `rose`/`azure` classes; no "Add fees on top instead"; posting units 100, price 100, fees 250 gives cost 10,000, a 250 fee expense and cash out 10,250.

## U10 + U11 · Markets in Settings, and brokerages that trade in several

**U10 (build):** Settings gets a **Markets** section shaped like Currencies: the list of markets (one per price pack venue group: Egypt (EGX), Egyptian funds, US, Gulf, Europe) with a switch each. It is the existing `market_packs` setting (`lightning/market/packs.py` `chosen`, used in `routes/investments.py` ~720–840): move that chooser into Settings › Markets (keep one code path; the Investments page links to it). The instrument picker searches only enabled markets' instruments.

**U11 (build the first half):**
- A brokerage account gets **Markets it trades in** (type-and-pick of enabled markets; default the profile's first market, EGX). New table `account_markets(account_id, market_id)` by migration. Shown in the account form for Brokerage only.
- The investment form's picker searches only that account's markets.
- The brokerage page groups holdings **by market** (a category header per market with its total, A05/A11), each in its market currency with the base value.
- The Investments tab gets a market filter (chips, A10.2) when more than one market is held.

**U11 (Proposal, do not build):** cash in a second currency inside one brokerage (USD cash for a US market in an EGP account). Read how US instruments are bought today and write `docs/proposals/multi_market_brokerage.md`: options (one account with cash per currency vs. one sub-account per market currency), what the ledger and position code would need, the effect on Convert (U5), and a recommendation. Add an owner question as a GitHub issue if you can, else a NOW.md *Next* item.

Tests: Settings › Markets saves `market_packs`; a brokerage with markets EGX+US offers both in its picker and an EGX-only one offers no US ticker; holdings render grouped by market.

## U12 · "What is payday?"

- Answer (for the owner): it is the day of the month your salary usually arrives (1–31). Lightning uses it to expect the salary in the cash plan and forecast; it records nothing until the money arrives.
- `lightning/ui/templates/dashboard/salary_setup.html:7`: label **"Salary arrives on"** with the field reading "day [ 25 ] of each month" (a small number well inline in the sentence). Help line, one sentence: "Lightning expects it then; you record it when it arrives." Day 29–31 behaviour stays (last day of shorter months) but is not explained on screen.
- Glossary: Payday → "the day of the month the salary usually arrives". Test: the label text.

## U13 · Add a recurring item: short and compact

- `lightning/ui/templates/planning/item_form.html` (and its route): put it on `.form-grid` (designs 004 T11): Row 1 Name · Amount · Direction segment (Money in | Money out) · Category. Row 2 Repeats (segment: Monthly · Yearly · Every N…) · Day · Starts · Ends (optional). Row 3 Account · Notes. Fields that only one schedule uses show only for it (A10.1). Max width ~960px so it never spreads across a wide screen.
- Remove help lines per U8. The phone stays one column.
- Test: the form uses `.form-grid` and has no field shown for a schedule not chosen.

## U15 · Ratio thresholds that colour the cards

Today each Financial health figure has **one** limit (`settings/financial_health_section.html`, `HealthService`). Make it three bands with defaults the user can edit.
| Figure | Good | Watch | Needs you |
|---|---|---|---|
| Emergency fund (months) | ≥ 6 | 3 to 6 | < 3 |
| Savings rate | ≥ 20% | 10 to 20% | < 10% |
| Debt to net worth | ≤ 30% | 30 to 70% | > 70% (the owner's example) |
| Fixed costs to income | ≤ 50% | 50 to 70% | > 70% |
| Any other ratio card that has a limit today | its limit = Good boundary | — | Claude's judgment, documented |
- Storage: two settings per figure (`<key>_good`, `<key>_alert`); migrate the existing single limit into `_good`. Validation: good and alert on the right sides for the figure's direction.
- Settings row: "Good from [ ]  ·  Needs you from [ ]" + Restore defaults. "No limit" stays.
- Display (A08): the card's chip says **Good / Watch / Needs you** with A08.2 tints (green tint, quiet, rose); the meter shows the two boundaries. **Needs you** also gives the card a soft rose background (`--rose-soft`), the owner's request; write this into A08 as the one case a KPI card is tinted. Watch is quiet (no tint). Apply wherever these figures show: Health tab KPI cards and rows, and the Overview if it shows them.
- Logic lives in `HealthService` (a `band(key, value) -> "good"|"watch"|"alert"`), never in templates.
- Tests: debt-to-net-worth 75% → alert card with the rose class; 50% → watch; edited thresholds change the band; the old single limit migrates to `_good`.

---

## Close-out (build agent)

- Changelog line per branch (`2026-10-15 · Claude:`), ≤ 3 lines. Architecture, Glossary, guideline (A08, A10, A14) updated as named above.
- Mohab and A16 per visible branch; number-audit around U7 and U11; full suite once at the end.
- Whatever is not built: one `report/` file each, `python tools/report_index.py`, NOW.md *Next* with **Read:**.
