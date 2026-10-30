# Audit 12: the PC app, tab by tab - clutter, hierarchy and flow

Date: 2026-10-30 · Author/reviewer: Claude (guideline-audit skill)
Repository: app · Reviewed commit: 94499084000e17b2f0c16bf0410df132936cb6db
Historical ID: audit-12 · Status: **plan for the owner's review; nothing built** · Plan item: [IV-3AM](../../issues/3-polish-and-arabic/3AM-pc-declutter-tab-by-tab.md)

## Scope and method

The owner asked for a full UX and visual audit of the PC app, tab by tab and button by button, focused on clutter.
The owner also sent an outside AI report on the desktop layout. The order was to read the pages first, then the report,
then write a plan to review together before building anything.

The sample household (`python -m lightning --sample`, Mohab's 2026, "today" 2026-10-02) ran in Chromium at
**1366 × 768** (a common Windows laptop) and **1920 × 1080**. All 24 section tabs plus an account page, Weekly review and
Needs you were captured and measured with [evidence/capture.js](evidence/capture.js). The measures were page length in
screens, figures, targets and live inputs ([evidence/metrics.json](evidence/metrics.json)). Row edit, a Budget group
and a gear were also clicked. Rules: guideline Part A (A05 headers, A07 cards, A09 page order, A16).

**The test for every page:** at 1366 × 768 the first screen shows the page's answer (the Lead), what needs you and the
daily action. Nothing on the page contradicts a figure on another page. Every control sits where the guideline puts it.

| Page | Screens at 768 | Figures | Targets | Live inputs | Verdict |
|---|---|---|---|---|---|
| Overview | 1.8 | 27 | 63 | 1 | good Lead; KPIs below the fold; a gear on its own row |
| Spending | **4.5** | 34 | 37 | 1 | day-2 charts say nothing; a KPI alone in its row |
| Budget | 2.8 | 48 | 92 | **15** | header on two rows; five progress visuals; edit grid inside the read view |
| Cash planning › Plan | 3.7 | 33 | 31 | 1 | good; bills repeat Budget's; Zakat card alone |
| Safety › Reserves | 2.2 | 21 | 53 | **25** | **titled "Cash planning"; contradicts Limits** |
| Safety › Limits | 1.7 | 8 | 22 | 1 | "All good" beside "Unavailable"; its own date control |
| Investments › Holdings | 3.2 | **91** | 30 | 4 | Lead half empty; header on two rows |
| Transactions | **4.7** | 33 | **139** | 14 | **4 rows above the fold**; Balance column all "—" |
| An account `/accounts/1` | 4.4 | **95** | **144** | 13 | same filter clutter; decimals |
| Accounts | 1.9 | 31 | 20 | 0 | ragged two-column cards; a duplicate column |
| Settings › Counterparties | **4.1** | 0 | **336** | **112** | **controls overlap**; every row an edit form |
| Settings › Categories | 2.0 | 0 | 255 | 69 | two columns to read across |
| Settings › Data checks | 1.9 | 6 | 11 | 1 | five big cards of "0.00" when all pass |

## Findings

Severity: **high** = wrong, contradictory or broken on screen, or the page's answer is off the first screen;
**medium** = clutter a user meets every day; **low** = polish.

### S. The shell (every page)

- **S1 high · the sidebar hides its own ends.** The accounts list makes the sidebar 1,274 px tall. At 768 px only four
  accounts show; *Add account* and *Manage accounts* sit at y = 1,250, so you have to scroll the sidebar to reach them.
  At 1080 they are still off-screen. With ten accounts in the sample, a real profile with 15 is worse.
- **S2 medium · the header splits onto two rows when a page has a second action.** Budget (period + *Fill this month*)
  and Investments (period + EGP/USD) grow to 154 px, so the content starts at about y = 260 instead of 200.
- **S3 medium · a gear alone costs a whole row.** Overview and Budget have one tab each, so the tab bar shows only a gear,
  floating right on an otherwise empty 80 px row (y 120-200). A05 puts the gear at the end of the tab bar; with no tabs
  there is no bar to put it on.
- **S4 medium · Transactions is the sidebar's name for five pages.** Accounts, Import, Held for others and Zakat all light
  "Transactions" in the sidebar. A person looking for *Accounts* or *Zakat* won't look under Transactions. Zakat also
  shows a card on Cash planning.
- **S5 low · "In your accounts 981,704" is printed three times on one screen**: in the sidebar, in the Transactions header
  and again on Accounts. A09.2 says one home per figure.
- **S6 low · "Review activity"** is a bare black word above the filters on Transactions and every account. It looks
  like a heading, not a link (A05: actions go right, quiet).

### O. Overview › Summary

- **O1 medium · the KPIs are below the fold at 1366 × 768.** The Lead (Net worth + Over time) fills y 200-645, and
  Needs you starts at 660. *Safe to spend* and *Left in plan*, the two figures people open the app for, start at about
  y 910. A09's order is right; the gear row (S3) and the Lead's height are what push them down.
- **O2 medium · Needs you rows are full-width rose slabs.** Each row is 56 px of pink fill, and "Manage Needs you" and
  "Weekly review" float in the heading line with no button look. Rose means *bad* (A03); a certificate payment waiting
  to be matched is a to-do, not a loss.
- **O3 low · "Get set up" and "Your position"** are two closed sections at the end with nothing in them until opened, and
  each takes about 90 px.

### SP. Spending

- **SP1 high · on day 2 of a month every chart is empty or one colour at 100%.** There is a full-width treemap with one
  tile, a two-bar chart, a calendar with one coloured day and a one-ribbon Sankey. A09.2: "never a chart of one colour at
  100%". The page is 4.5 screens long and says one thing: 3,410 on groceries.
- **SP2 medium · the KPI card stands alone in its row**, 360 px wide on a 1,050 px canvas (A16: a card alone in its
  row). The tab says *Spending*, the title says *Expense analysis*.
- **SP3 low · cards inside cards:** "How each one moved" and "Inside its usual range?" sit as a card inside the category
  card (A07, A16).

### B. Budget

- **B1 high · five progress visuals answer one question.** There is a three-colour meter in the Lead, the pace chart, an
  *Everyday spending* bar, a *Plan leaves to save* bar, 12 *Spent of plan* bullets and the group roll-up. They use three
  different visual languages, and the user can't tell which one is "the" answer.
- **B2 high · the read view is an edit grid.** Opening a group shows 10 rows of live "Amount or %" inputs (5,217.00
  with decimals), plus Income % and 3m/6m buttons. There are seven numeric columns; Base budget equals Planned and
  Carryover is 0 on every row, because the sample has no carryover. 15 live inputs on a page you open to *read*.
- **B3 medium · Spent of plan lists 12 rows; 11 show "0 of …".** At the start of a month it is a long list of empty bars.
  Bills in this month's plan beside it is half its height and leaves a 400 px hole.
- **B4 medium · "System Categories · Loan payments, Zakat"** leaks an internal group name into Spending by group
  (also in 3G, still there).
- **B5 low · the bills list here and "The next 30 days" on Cash planning are the same seven bills** with the same *Mark
  paid* buttons, and *Bills to pay 18,460* = *Due before payday 18,460* (A09.2: one home, a link).

### C. Cash planning

- **C1 low · the waterfall labels wrap to four lines** ("Gam'eya instalments before next income"); the bars are readable.
- **C2 medium · cards alone in their rows:** *Can I afford this?* is a full-width card around one field and one button.
  *Zakat* is a full-width card for one figure. *What you owe* repeats Overview's 66,500.
- The outside report's "overlapping timeline badges" no longer exist: the 30 days are a list.

### SA. Safety

- **SA1 high · Reserves is titled "Cash planning"** while the sidebar says Safety and the tab bar says Reserves/Limits.
- **SA2 high · the two tabs contradict each other.** Reserves opens on a rose banner: *Emergency fund covers 0.5
  months*. Limits says *All 5 figures are within your limits · All of them are good*, then lists Emergency fund as
  *Unavailable · 6.1 months in cash you own*, and *Debt to cash 28.1% · No limit* with a rose bar. That is three answers
  to "am I safe?" on two tabs of one section.
- **SA3 medium · Limits has its own "As of [date] Show" control** instead of the period control (A05: one period
  control, one source). Data checks does the same.
- **SA4 medium · Reserves is a form, not a page.** It has 25 live inputs (*Amount set aside 20,000.00*, each goal's
  *4,500.00*) and a seven-item bullet list, *Could also use*, inside the Emergency fund card.
- **SA5 low · the Savings rate line has no axis** (3S #3, still there), and the page ends with "Change them behind the
  gear", which explains the screen instead of designing it.

### I. Investments

- **I1 medium · the Lead's left half is empty.** It says *752,486 · 0 Net gain or loss*, which reads as broken on day 2,
  over 300 px of blank card. The donut's legend, the locked certificate, Brokerage cash and Holdings after sale are
  crammed on the right.
- **I2 medium · "By currency" is a full-width card for two rows** (A16: a card alone in its row).
- **I3 low · the Prices tab:** "Where prices come from" collides with the *Update prices* button, and each row has two
  wide grey wells, one of them empty (Total value).
- The outside report's "quantity and grams mashed together" is not shown on this table: the columns are Cost, Value,
  Total gain and Total return.

### T. Transactions and an account

- **T1 high · four transactions above the fold at 1366 × 768.** The first row starts at y = 543. Above it are the
  header with a three-figure strip, the tab bar, the bare "Review activity", a filter row and "Show value updates (28)".
- **T2 high · the filter row is unaligned.** "Date period" floats as a label over one control. The search placeholder is
  cut off ("catego"). There is a raw `yyyy-mm` box beside a date-preset select, two ways to say the same period. *Views*
  and *Find and replace* are two different button styles.
- **T3 medium · on the all-accounts view the Balance column is "—" on every row**, a whole column that says nothing.
- **T4 medium · figures carry decimals:** -3,410.00, 157,582.22 EGP and 50,000.00 EGP → 1,000.00 USD (A16: whole EGP
  on big figures). The account page repeats "EGP" in every balance cell.
- **T5 medium · the new-transaction row is always open at the top** with five wells. It is fast for typing, but it
  looks like a data row, and on a 768 screen it takes one of the four visible rows.
- **T6 low · the header strip shows "Held for others −7,100"** on Transactions and **6,900** on the account page, for the
  same money. One is a signed total, the other a share, and neither says so.
- The outside report's "columns jump when a row is edited" was not reproduced: the header widths are identical before
  and after (41/136/229/199/129/142/119 px). Edit reloads the page with `?edit=`, and the Notes well shrinks to "Loan…".

### A. Accounts

- **A1 medium · two columns of cards of uneven height leave holes.** Deposits (one row) sits beside Cash & bank (four
  rows); Gam'eya stands alone in the last row.
- **A2 medium · "In your accounts" and "What you own" are equal on 9 of 10 rows.** The column says something only for
  CIB Payroll. A05 says "What you own only when it differs".
- **A3 low · Other currencies and From SMS** are header buttons that aren't about accounts (3G, still there).

### ST. Settings

- **ST1 high · Counterparties: the buttons overlap the field.** *Open / Person / Business* are drawn over the
  "Suggested category" well, so it reads "Learned: Eatin" under the buttons. Each of 36 rows is a live form: 112 inputs and 336
  targets on one page.
- **ST2 medium · Categories puts two lists side by side** (A09.2: never two columns to read across). Each row has five
  controls (name well, type chip, Recurring/One-off, +, archive, delete).
- **ST3 medium · Data checks gives each passed check a full card** with Actual 0.00 / Expected 0.00 / Difference 0.00.
  When all pass, it is a wall saying nothing; only a failure needs the card.
- **ST4 low · Your data shows the database path** `/home/user/…/sample.db` under App version (3G, still there).
- The outside report says there is "no master settings panel". There is one: *Settings in each tab* on Your data
  links every gear. It sits fourth, below Features, as a plain list of links.

## The outside report, claim by claim

| Claim | Verdict |
|---|---|
| Triple-stacked top bars, about 180 px | **Partly held.** Two bars, not three. Content starts at 200 px; 260 on Budget and Investments (S2, S3) |
| Sidebar accounts push Settings off-screen | **Held for Add/Manage accounts** (S1); Settings itself stays visible, as the nav is above the list |
| Global actions compete with page actions | **Not held.** Search and privacy are in the sidebar; the header has only period, Undo and page actions |
| Gear contexts are hidden | **Partly held.** A gear alone on a row reads as decoration (S3); Settings links them all (ST4 note) |
| Double period disconnection | **Held** for Limits and Data checks (SA3). Cash planning follows the header |
| Accounts tab duplicates the sidebar | **Partly held.** The list repeats the sidebar's figures, but it adds groups and What you own (A2) |
| Needs you competes with the headline | **Partly held.** Rose slabs (O2), but below the Lead, as A09 orders |
| Three stacked 50/50 split cards on Overview | **Not reproduced.** Overview is now Lead, Needs you, four KPIs |
| `<details>` reflow jumps under Net worth | **Minor.** The rows expand in place inside the Lead; the chart beside it stays put |
| "If you sold today" belongs in Investments | **Already done.** It is not on Overview; Holdings after sale is on Investments |
| Spending: three dense visualisations | **Held differently.** The problem is empty charts early in a month (SP1) |
| Spending rows are dead ends | **Not held.** Treemap tiles and Budget bullets open the filtered register |
| Health sparklines hide the data | **Held** (SA5, 3S #3) |
| Health "Watch" has no edit-target link | **Held** (SA2, SA5: "behind the gear") |
| Budget stacks six notices | **Possible in code** (`budget.html` has 6 notice slots), **not seen** on the sample |
| Budget: competing progress indicators | **Held** (B1) |
| Budget: live inputs in read rows | **Held** (B2) |
| Budget: 8-column sub-table | **Held** (7 numeric columns, B2) |
| Carryover bridge leaves the page | **Held** in code; not reachable on the sample (no carryover) |
| Cash planning: waterfall slivers | **Partly held.** Small bars read; labels wrap (C1) |
| Cash planning: overlapping timeline | **Not reproduced.** Now a list |
| Obligations spread over four pages | **Held.** Bills on Budget and Cash planning, loans on Loans, gam'eya on Accounts (B5) |
| Investments: heterogeneous grid | **Not held** on this table (I3 note) |
| Investments: FX not separated | **Partly held.** "Of your total gain 44,559, 2,206 came from exchange rates" exists, as one line (I2) |
| Investments: can't add a holding | Not checked in this pass; 3G §4.8 covers it |
| Register: heavy filter stack | **Held** (T1, T2) |
| Register: quick-add row distracts | **Held, mildly** (T5) |
| Register: row edit jumps columns | **Not reproduced** |
| Register: review modal interrupts typing | Not triggered on the sample; it fires only for a new name |
| Register: reserve prompts break the ledger | Not on the sample; the code exists (`tr.reserve-match-prompt`) |
| Settings tabs look like work tabs | **Held, low.** Same pill bar everywhere, as A05 requires |
| Data checks is a narrative wall | **Held as a card wall** (ST3) |

Its "fix" table needs care against the guideline. Some of what it proposes the guideline forbids or decides
differently: a 56 px merged header (A05 fixes the header's parts), a slide-over drawer instead of in-place rows, a
transaction modal instead of the inline row (the PC flow is keyboard-first), and capping the sidebar at four accounts.
The plan below keeps its aims and uses the guideline's own parts.

## The plan (for review; nothing built)

Four steps, each one shippable and testable on its own: IV-3AM1 to 3AM4. The item stays *new* until the owner agrees;
each finding's code (S1, B2…) goes with it.

**Step 1 · Wrong on screen (high, small):** fix what contradicts or breaks first.
1. SA1 Reserves takes Safety's title. SA2 one emergency-fund answer on both Safety tabs: Limits reads the Reserves
   figure, and "All good" never sits beside "Unavailable"; *No limit* rows draw no rose bar.
2. ST1 the Counterparties row stops overlapping. The category well gets its own column, and the three buttons go behind
   ⋯ or into an edit drawer.
3. T3 the Balance column hides on the all-accounts view. T4 the register shows whole EGP, and the account page drops
   "EGP" from every cell.
4. B4 "System Categories" gets a user name or folds away.

**Step 2 · The shell gives back space (medium, shared CSS/template):**
1. S1 the sidebar: Add/Manage accounts move to the accounts heading line (a + beside "Accounts"). The list scrolls
   inside itself, with groups collapsible and the active account kept in view.
2. S3 a gear with no tabs moves into the header's action slot, beside the period control, instead of a row of its own.
   **Owner decision:** A05 places the gear at the tab bar's end, so this needs a one-line guideline change in both
   repos.
3. S2 a second page action goes into ⋯ when the header would wrap, so the header stays one row at 1366.
4. S6 *Review activity* becomes a quiet right-aligned link in the header actions or the ⋯ menu.
   Target: content at y ≤ 140 on every page at 1366 × 768.

**Step 3 · Each tab opens on its answer (medium, per page):**
1. Overview (O1, O2): a shorter Lead (Over time capped to the Lead's figure column height) so the four KPIs show at 768.
   Needs you rows become neutral rows with a coloured mark, not rose slabs; Manage and Weekly review become proper
   quiet links.
2. Budget (B1-B3): one Lead meter plus the pace chart. *Spent of plan* shows rows with spending or over plan first, the
   rest folded ("9 untouched"). The group rows are read-only, with an **Edit plan** toggle (as the phone's Budget already
   has, IV-3AL) that turns on the inputs. Base/Carryover columns show only when carryover exists. Budget's bills card
   becomes a link row to Cash planning's list (B5).
3. Transactions (T1, T2, T5, T6): one filter line (search · period chip · category/tag · Views ⋯) aligned to the table.
   The `yyyy-mm` box is dropped (the period control already says it). The header strip shows only what differs. The
   new row stays (keyboard-first) but is styled as an entry row. Target: 10 rows above the fold at 768.
4. Spending (SP1-SP3): early in a month (under 7 days or under 3 categories) the page leads with last month's complete
   picture, plus a one-line "so far" for this month. Single-tile charts give way to a sentence. The title matches the tab.
5. Safety (SA3-SA5): Limits uses the period control; Reserves shows set-aside figures read-only with an Edit per goal.
   *Could also use* folds to one line. The Savings rate line gets its axis. Each Watch row links straight to its limit's
   setting.
6. Investments (I1, I2): the Lead's left side gets its working (Cost, Unrealized gain, the FX share). By currency joins
   the Lead or pairs with Income collected.
7. Accounts (A1-A3): one column of groups (or a grid that doesn't leave holes). What you own shows only where it
   differs. The header keeps Add account, and the rest goes in ⋯.
8. Cash planning (C1, C2): *Can I afford this?* moves into the Safe-to-spend Lead. Zakat and What you owe become rows or
   pair with a neighbour.

**Step 4 · Settings stop being forms (medium):**
1. ST1/ST2 Counterparties and Categories become read-only lists (one column, A09.2), with a click to an edit drawer;
   bulk actions stay.
2. ST3 Data checks: passed checks collapse into one line ("5 checks passed"); only failures get a card, with its fix.
3. ST4 the database path goes behind Advanced. *Settings in each tab* moves to the top of Your data.

**Not in this plan (already filed elsewhere):** investments entry flow (3G §4.8, 5G), Needs-you as the smart inbox (7L),
card system (3Q), chart fixes (3S). Each step links them where it touches them.

**Owner questions:**
1. S3: may the gear move into the header when a page has no tabs? This changes guideline A05 in both repos.
2. S4: should Zakat and Accounts stay under *Transactions*, or should Accounts get its own sidebar entry? (8 sections is
   the current cap in `sections.py`.)
3. B2: an *Edit plan* toggle on Budget, or send all editing to the existing *Fill this month* page?
4. T5: keep the always-open new-transaction row (fast for keyboard users), or open it on `N` / *Add*?

## Validation and limits

- Desktop Chromium only, LTR English, the light theme, the sample household on 2026-10-02 (day 2 of the month: SP1 and
  B3 are worst at the start of a month and ease later). Arabic RTL, dark themes and the WebView2 shell were not checked.
- Interactions checked: row edit, a Budget group, the Overview gear. Not checked: the review modal, reserve-match
  prompts, carryover bridge, Budget's notice stack (none fire on the sample).
- Re-run: `python -m lightning --sample --no-browser`, then
  `NODE_PATH=$(npm root -g) node reports/2026-10-30-desktop-tab-audit/evidence/capture.js <out>`.

## Dated follow-ups

### 2026-10-30 · the owner's answers, and a second pass: words, visuals, size

**Owner's answers:** 1. **No**: the gear stays at the tab bar's end (A05 unchanged); S3 is solved inside A05 by
making a gear-only bar take no row of its own. 2. **Stay**: Accounts and Zakat stay under Transactions; S4 is dropped.
3. **An Edit button on the Budget page** (as on the phone). 4. **The new-transaction row stays at the top**; T5 only
restyles it as an entry row.

The owner then asked for three more checks: "we tend to overexplain things, I want the page to look polished"; "new
tabs we created have no visuals"; "sometimes the form or card is just taking too much space for no reason". Measured on
all 26 pages at 1366 × 768: explanatory sentences of six words or more, charts (SVG over 60 × 30 px), and cards
over 120 px tall whose text covers under 12% of their area.

**P1 · over-explaining (medium, every page).** Sentences that describe the page, its method or a chart's legend:

| Page | Says | Fix |
|---|---|---|
| Reports | "Ready-made comparisons and your saved views" (a description under the title, A05 forbids it) | a status sentence from its figures |
| Import | "Drop your bank files; each one is matched to its account." · "Each account opens its own review: duplicates are flagged…" · "Undo removes every entry a file created…" | cut; the drop zone says it |
| Prices | a two-sentence subtitle, then "Lightning updates the prices… by itself", then "A price you type wins…" again | one status sentence ("Prices from 2026-09-30; next update after 2026-10-31") |
| Limits | "Limits only compare figures you already have…; change them behind the gear." | cut |
| Data checks | an intro paragraph, one method sentence per check, and a closing paragraph | cut the intro and the closing; method behind the check's info tip |
| Zakat | two paragraphs: the lunar year, "a scholar answers your own case…" | one line under the Lead; the rest behind an info tip |
| Needs you / Weekly review | "Reviewed items stay quiet…" · "Reminders use your existing plans… Native alerts require…" | cut, or one line |
| Planner | "Every class below its target gets the same share of its gap…" | behind an info tip on the two choices |
| Loans | "Every unpaid payment, due or upcoming. Only payments already due come off free cash." | cut |
| Reserves | "0 EGP set aside in reserves; free cash is 163,701 EGP after them and bills due." | cut (Cash planning owns free cash) |
| Cash planning | "Solid: what it was · dashed: the forecast" · "Money in includes income, CD proceeds and a gam'eya payout · projected values are estimates" | the legend says it; cut |
| Spending | "Lowest month on the left, highest on the right · the tick its middle month · the dot now" · "less to more spent · the biggest day darkest" · "So far · comparisons use the same calendar days…" | the key says it; cut |
| Settings | "Applies at once and saves with this profile." · "One is made each time the app starts." · "Lightning does not upload your data…" | keep only hints that change what you do |
| Recurring | "Repeated about monthly. Track one to plan for it." | cut |
| Budget | "Day by day against the plan, bills and loan payments left out." | the chart's key |
| Weekly review | each card's heading repeats its only row word for word (A16: a line that repeats its label) | one list of Needs you rows, no card per item |

The rule for the fix: a sentence stays only if it reads a figure ("2,122 over the plan's pace") or changes what the user
does next. A method goes behind the existing info tip (`info-tips.js`) or the page's "How it is worked out" link. A
chart's key replaces any sentence that describes the chart.

**P2 · tabs with no visual (medium).** No chart on Compare periods, Reports, Loans, Planner, Prices, Import, Held for
others, Zakat, Weekly review or Needs you. Recurring has bars, but its KPI stands alone. Each fix uses an existing
macro in `partials/charts.html` (`meter`, `bullet_row`, `bars`, `share_bar`, `diverging`, `lead_card`) and a figure the
service already computes:

| Tab | Visual |
|---|---|
| Compare periods | a Lead (Money out, this vs against) and `diverging`/`bullet_row` per category, biggest change first |
| Reports | each of the three comparisons as a KPI card with a two-bar or `meter` comparison (A08), not a bare figure |
| Loans | a Lead: Loans still to pay with paid-vs-left `share_bar` per loan; the payoff date in its working |
| Planner | per class, a `bullet_row` of current share with the target as the tick; the suggested split as `share_bar` |
| Zakat | a Lead: Still to pay 13,720, with a `meter` of zakatable wealth against the nisab and paid against due |
| Held for others | a `share_bar` by person (or one row when one person) inside a Lead with the total |
| Prices | each row's last-price date as a freshness mark (A03 meaning colours) instead of a second wide well |
| Import | none needed; cut it to one card (P3) |

**P3 · cards and forms bigger than what they hold (medium).** Cards over 120 px with under 12% text, and forms
wider than their values:

- Lone cards around one thing (A09.2: never a full-width card around one button): Reports' *Saved views* (3 links)
  and *Everything* (2 buttons); Import's "vodafone-october.csv is waiting" (one button, already a Needs you row);
  Held for others' empty *Investments* card; Cash planning's *Can I afford this?*; Accounts' *What you own* Lead (left
  half empty); Investments' *By currency*; Loans' *Loans still to pay* (a figure and a sentence across 1,046 px).
- Oversized fields: Planner's *Amount in EGP* is 760 px for a five-digit number; Compare's period form fills a card
  with two date pairs, a chip set and a select; Prices' two 200 px wells per row; Reserves' *Amount set aside* well.
  A10 widths apply: a money field fits its value. Forms sit on one line where they fit.
- KPI cards alone in their row: Recurring's *Fixed costs to income*, Spending's *Money out so far*, Data checks'
  three cards (a fourth slot empty).
- Compare periods and Reports draw their figures in another type (letter-spaced, with decimals: 315,748.75 EGP);
  they must use the KPI card (A08) and whole EGP.
- Loans' progress bars are labelled "Pay early" (the link above them), not what they show (9 of 24 paid).
- Weekly review: one card per item (five cards for three rows); Held for others: three closed cards at the end.

These join the plan as **IV-3AM5** (words, visuals and sizes), built with each tab's step where it overlaps.
