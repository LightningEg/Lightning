---
title: Visual audit - every KPI card should answer, compare and point; one card system for PC and phone
type: polish
area: product
status: ready
created: 2026-10-19
by: Claude
skills: guideline-audit
app_version: 1.3.0
commit: 84120ab
repo: both
---

## Report

**Brief from the owner (2026-10-19):** the cards, key cards and KPI cards are unsatisfying. Budget opens with one wide
"Categories over plan" card and nothing else; Cash planning's Free cash card says nothing. Space is valuable: give every card
a comparison or a subtle fact. Go tab by tab, report what can be better, aim for the best budgeting and wealth app there is.
Audit first; the guideline may change after.

**How I looked.** `python -m lightning --sample` with `LIGHTNING_TODAY=2026-10-19`, prices offline, PC 1440 × 900, every tab
plus a holding and an account page; phone with `tools/phone_check.py --shots`. Each card's size and text were measured in the
browser. To reproduce the owner's Budget screen I recorded two test expenses (Eating Out 2,600 and Food & Groceries 2,400 on
2026-10-18); Budget figures below include them, other tabs are the untouched sample. 3G and 3H findings are not repeated
unless visual and still visible. The owner has the illustrated version (screenshots and mock-ups) as a private page.

### 1. Seven problems across every tab

1. **A figure with nothing to compare it to.** 19 of the 33 KPI cards on the main PC pages show no reference (last month, plan,
   target, usual, today). Free cash's support line is set to `""` (`lightning/ui/routes/planning.py:133`); Accounts shows
   596,179 beside 602,179 without naming the 6,000; Currencies' four cards, Loans' three ratios, the holding page's Current
   value and Return stop at the number.
2. **The grid, not the content, sets the size.** `.main .stat-tiles` is `repeat(4, …)` (`style.css:1987`): Recurring's one
   card and Spending's one card early in the month fill a quarter of the row. `.key-notes` is `auto-fit` (`style.css:1562`):
   one note stretches full width (Budget, Loans, Reserves), against A07 "Alerts live inside the card they concern".
3. **Seven KPI designs:** A08 tile, key-note strip, Currencies `.metric-card` (also nested in the USD card: A16 card in a
   card), page-header figures (Transactions, account pages), Accounts summary, Loans gradient lead, Budget's three figures in
   the Planned card. CSS: 73 rules mention `.stat-tile`, 56 `.metric-card`, 44 `.key-note`; `style.css` has 414 `!important`.
4. **Slots move, so figures don't line up.** Cash planning: Safe to spend's figure sits 27 px above Free cash's.
5. **Dead and duplicate cards.** Investing rate 0.0% (Overview), Net gain or loss 0 (Investments, month), Spread paid 0,
   "No plan yet" at figure size, Reserves "−0" (Overview 2026-09). Holding page +13,218 and +14.9% twice; Spending 2026-09
   12,000 twice (Biggest category = Largest payment); Currencies repeats its FX cards in the USD card; the savings waffle on
   Overview, Budget and Investments.
6. **Charts sized for a full month, drawn for a thin one.** 2026-10: a one-tile treemap 770 × 230 px, one pair of clustered
   bars across 1,000 px; Overview Net flow leaves ~200 px blank; Cash planning's bridge column ends ~260 px before the
   timeline beside it; the day calendar uses two thirds of its card.
7. **Pictures that say the wrong thing.** Lowest point ahead's dot marks the last (highest) point; net worth axis to
   1,000,000 for 546,089; Spending's Average payment sparkline in Azure (A16 colour off meaning); the car loan's progress bar
   Meadow (principal paid is Azure, A03); phone Budget "Spent 18,824" in Azure text.

Keep: Spending's Money out card in a full month (the model for every KPI), Cash planning's bridge, Health's chips and limit
ticks, Late · N days with Mark paid, Month by month strip, the phone Budget lead card.

### 2. The proposal: a five-slot KPI card and three layout rules

**Slots, fixed and always present** (so baselines align): 1 label and chip (period or Good/Watch/Needs you/Late; no icon
tile, as C06 already does on the phone); 2 figure, Ink, whole EGP; 3 **comparison, compulsory**: since the last month end,
same days last month, usual, plan, target or today, signed and toned good/bad; 4 one micro-visual: sparkline (A12.1.15),
meter with pace or limit tick (A12.5.2), segmented bar of what the figure is made of (A12.3.2 share bar, revived), mini
timeline (A12.7.3), mini columns; the dot marks the point the label names; 5 one muted line of context or one action.

**Rows:** two to four cards that fill the row (`repeat(auto-fit, minmax(…, 1fr))`). **Never one alone:** a lone answer is a
Lead card with its Support card beside it; a key note never forms a row, it becomes the chip and action of its card.
**Thin data changes form:** a treemap needs four tiles, a clustered chart two categories, a line three points; below that,
ranked rows or a sentence; a chart with two marks shares its row.

Twelve A12 visuals are "Ready to use" and unbuilt; several fill the empty spaces: Pace (Budget), Step line (account
balance), Loan balance and Principal and interest (Loans), Histogram (Spending), Dumbbell (targets).

### 3. Tab by tab

| Tab | Today | Proposed |
|---|---|---|
| Budget | One pink strip "Categories over plan 2"; waffle repeated; Left in plan small inside Planned. "About 2,078 a day for 13 days" = 27,010 / 13, but 16,363 is bills still to pay (rent 12,000 late 16 days, car loan, utilities); everyday left is 10,647, ~819 a day | Row: **Left in plan** 27,010 with segmented bar spent 8,410 / bills to pay 16,363 / everyday 10,647; **Everyday spending** 8,410 by day 19, 3,270 under the plan's pace (11,680), +228 against 2026-09 (8,182); **Over plan** 1,239 in 2 categories as mini bullets, action Cover it from Entertainment (5,072 left; `budget_move.html` exists); **Plan leaves to save** 14,580, 29% against 20%. Below: A12.1.9 pace chart (everyday only, plan line, last month) beside "Bills in this month's plan" with Mark paid. Waffle leaves Budget |
| Cash planning · Plan | Free cash bare; Bills before income 1,370 ignores 15,090 late; Lowest point's dot on the highest point | **Safe to spend** 160,666, 86% of free cash, segmented bar (safe, budget 15,550, savings 10,000, due 1,370); **Free cash** 187,586, +11,500 since 2026-09-30 (176,086), month-end sparkline, footer of what it is made of; **Due before payday** 1,370 + 15,090 already late, mini timeline to payday; **Lowest point** 159,315, 28,271 below today, 4.5 months of spending, dot on the low. Bridge gains late bills as a step so both columns end together |
| Overview | Investing rate 0.0% dead; no Safe to spend; Net flow gap; axis to 1,000,000 | Row: Change in net worth, Savings rate against usual, **Safe to spend**, Left in plan. Net flow: six months of net flow as mini columns, this month hatched. Net worth: name the change (+303,927 since 2026-01, from 242,162) and add monthly change columns. No plan: "—" plus Make a plan, never text at figure size |
| Spending | 2026-10: one card in a quarter row, one-tile treemap, one-pair columns | Early month row: Money out so far (3,410 against usual 3,820, −11%), No-spend days 18 of 19, Bills not paid yet 16,363, Biggest so far. Under four categories: ranked rows. Calendar shares its row (biggest days or A12.6.1 histogram). Merge Biggest and Largest when the same money; Average payment line soft rose or cut |
| Health | KPI row repeats Against your limits; "6.9 months in cash you own" floats outside the card; trend charts have no limit line | Scorecard row: "5 of 6 within your limits" and the one that needs you with its second fact inside. Trends draw the target line |
| Currencies | Cards in a card; repeats; decimals on big figures; lines on top of each other | Standard row: Foreign money 114,211 (19% of what you own), FX gain +1,394 split unrealized 423 / realized 971, Rate now 51.60 against your cost 49.80 (+3.6%). Spread paid only when not zero. USD panel as rows |
| Recurring | One card, three quarters empty | Fixed costs 17,110 (34%, limit tick 50%), Subscriptions 7,080 a year (590 a month), Late 15,090 in 4 payments with Mark all paid. Bill rows whole EGP, late first |
| Loans | Three ratios without limit ticks; strip + azure gradient card for 37,500 (owed is soft rose); green progress bar; late payment unmarked | Row: Still to pay 37,500 (9 of 24, ends 2027-12-05), Next payment 2,500 Late · 14 days with Mark paid, Debt to net worth 9.2% with 30% tick. Each loan: A12.7.2 loan balance chart, principal paid in Azure, Meadow payoff dot |
| Reserves | Strong rose strip "0.6 months" for a household with 6.9 months of cash; six-line bullet list | One lead card: coverage bar (set aside 20,000, other cash 202,676, kept apart 21,016, fund 10,376, certificate locked 100,000) against the six-month target 212,523 and the 3-month mark; chip Watch, not Needs you, when cash you own covers the target |
| Investments | Waffle again; "Net gain or loss 0"; five classes; By currency card for two rows; empty half-card | Row: Portfolio value (keep), Total gain +44,559 split price ~25,850 / interest 16,500 / FX 2,206, Income collected 16,860 with monthly mini columns, Not in EGP 31% (replaces By currency). Four classes then Other. Hide empty cards. Holding page: one Gain card when equal; slots for cost against price (220.63 / 247.30 USD) and share (29%) |
| Accounts | 596,179 and 602,179 unexplained; Transactions count column; alphabetical; account page has no chart | Row: What you own (6,000 more is Mom's), Cash you own 243,692 (41%), Invested 352,486 (59%), Held for others 6,000. Table grouped like the sidebar with share bars. Account page: A12.1.5 step line and This month in/out/net; no "EGP" on every balance row |
| Phone | Closest to target | Budget Spent in Ink, not Azure; tiles gain the comparison line; over-plan becomes the lead card's last row |

### 4. Guideline changes (made in guideline 3.32, 2026-10-19, both repos)

- **A07:** a card is sized by the row and never left alone in it; a lone answer is Lead plus Support.
- **A08:** the five fixed slots; comparison compulsory; no icon tile; shared baseline. **A08.3:** replace the Budget example
  ("Categories over plan · 2 · Personal and Work") with Left in plan and an Over plan Needs-you card. **New:** zero and empty
  KPIs show "—", the last value and date, and what would move it; text never at figure size.
- **A09:** two to four KPI cards fill the row; key notes never form a row.
- **A12:** thin-data forms; a sparkline's dot marks the point its label names; **A12.3.2** share bar back as the KPI segmented bar.
- **A16:** add "A figure alone: compare it." and "A card alone in its row: pair it." (AGENTS.md copy and
  `tests/test_docs_structure.py` follow).
- **C06:** the tile's one line is the comparison.

### 5. How to build it

- A `Kpi` dataclass with required `compare` and a typed optional `visual`, built in one module from service figures (never
  in templates or JavaScript), replacing the ad hoc dicts in `_plan_stats`, `_ratio_tile` and the dashboard.
- One `kpi_row` macro and one CSS block; retire `stat_tiles`, key notes at page top, `.metric-card`, page-header figures and
  the Accounts summary, deleting each old CSS layer as its page moves.
- `tests/test_brand_audit.py`: every KPI row holds 2–4 cards; every KPI has a comparison; no duplicate KPI values under two
  labels; baselines in a row within 2 px; no card in a card. Mohab steps for the Budget over-plan card and Free cash's comparison.
- Arabic: segmented bars and timelines mirror, numbers and time axes don't (A06.2). Website: site-recapture after Overview,
  Budget, Investments or Cash planning change.

### 6. Order

1. ~~Owner answers; guideline change in both repos~~ done 2026-10-19 (guideline 3.32, app and website PRs).
2. **Next:** KPI component, Budget and Cash planning (number-audit for the everyday day rate).
3. Overview, Spending thin-data forms, Recurring, Loans, Reserves.
4. Investments, holding page, Currencies, Accounts, account page.
5. Phone, arabic-check, Mohab, site-recapture.

Small fixes that need no decision may go first: phone Budget Spent in Ink; Lowest point's dot on the low; Reserves "−0";
Average payment line soft rose; loan progress in Azure; Currencies card in a card.

### 7. Owner's answers (2026-10-19: "yes to all five, update the guideline now")

1. The five-slot card, without the icon tile on PC: yes (A08.1).
2. Budget's day rate counts only everyday money, leaving out bills still to pay in the plan: yes. A figure change: number-audit
   before it ships, and the Glossary names the new figure.
3. Price and net-worth charts keep "one axis, from zero"; a trend that moves little names its change and adds monthly change
   columns (A12). Read as the first option; ask the owner if a zoomed axis is wanted after all.
4. The savings waffle lives only behind the Overview's Savings rate: yes (leaves Budget and Investments).
5. Guideline first: done in 3.32. Also asked the same day: Arabic body text is Noto Sans Arabic instead of IBM Plex Sans Arabic
   (app fonts, website `css/arabic.css`, A06.2, B04, C10).
