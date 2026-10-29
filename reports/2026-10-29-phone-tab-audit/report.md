# Audit 10: the phone, tab by tab - quick actions and the answer first

Date: 2026-10-29 · Author/reviewer: Claude (guideline-audit skill)
Repository: app · Reviewed commit: 045ccd48dcb6a0d69605f6e0226259dcd823f119
Historical ID: audit-10

## Scope and method

The owner: the phone still looks cluttered and unpolished; audit each tab for what it should look like when the phone is
for **quick actions and quick information, not deep analysis**. The owner also sent a tab-by-tab breakdown of the five
slots (2026-10-29); each of its claims was checked against the running app below and is marked held, partly held or not
reproduced.

The phone app (`profile_app(..., phone=True)`) ran on a dummy profile with the sample household, in Chromium at
360 × 800 with touch, on 2026-10-29. Each page was captured whole and first-screen, and measured: length in screens,
figures, tap targets, targets under 40 px tall and cards ([evidence/capture.py](evidence/capture.py)). The bottom
clearance above the tab bar was measured with each page scrolled to its end. Rules: guideline Part C (C01-C12) and A16.

**The test for every tab:** the first screen (about 680 px between the app bar and the tab bar) holds the tab's one
answer, the one or two things a person does there daily, and the latest money; anything that explains, compares or
charts is one tap away, never stacked under it.

| Page | Screens long | Figures | Targets | Under 40 px | Verdict |
| --- | --- | --- | --- | --- | --- |
| Overview `/` | 1.9 | 12 | 56 | 1 | close; nesting and stray link |
| Budget `/budget` | 2.6 | 24 | 54 | 0 | the budget shown twice |
| Transactions `/transactions` | 6.2 (paged) | 45 | 70 | 0 | opens on All time; header heavy |
| More `/more` | 1.6 | 5 | 17 | 0 | a card of buttons on top |
| Cash planning `/plan` | 2.8 | 24 | 14 | 1 | a zero hero, then analysis |
| Investments `/investments` | 3.1 | 31 | 24 | 1 | chart before holdings |
| Accounts `/accounts` | 1.2 | 12 | 14 | 0 | good: the model to copy |
| An account `/accounts/1` | 7.1 (paged) | 106 | 84 | 3 | opens on All time |
| Financial health | 2.7 | 8 | 21 | 9 | the problem comes third |
| Spending `/birdview/expenses` | **6.1** | **71** | 66 | **14** | a PC report on a phone |
| Weekly review `/review` | 1.2 | 1 | 10 | 1 | wrong slot, cut word, repeats |

## Findings

Severity: **high** = the tab's first screen does not answer its question or bury its daily action; **medium** = clutter a
user sees every day; **low** = polish.

### The five slots

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | medium | **Overview: two attention blocks around the month stepper.** When a payment is due today or tomorrow, its card sits above the stepper and Needs you below it (`phone/dashboard/index.html`, `phone.soon`). Owner's claim **held** (the sample on 10-29 has no such payment, so only Needs you shows). Expected: one Needs you strip under the stepper; "N due today or tomorrow" becomes its first item and part of its summary line. | [1-overview.png](evidence/1-overview.png) | IV-3AL1 |
| F2 | low | **Overview: "Manage Needs you" sits loose** under the card, as body text, on every visit. **Held.** Expected: the last row inside the opened Needs you list. | [1-overview.png](evidence/1-overview.png) | IV-3AL1 |
| F3 | medium | **Overview: folds three deep.** Your position › If you sold today › Holdings after sale › each class; This period has six folds with charts inside. **Held.** Expected: Your position as four flat rows (own, cash, holdings, owe), each opening its page; This period as one row per figure that opens a **sheet** (C09), never a fold in a fold. The charts stay one tap away. | template | IV-3AL1, owner D1 |
| F4 | - | **Overview: content under the tab bar.** **Not reproduced.** `main` has 104 px bottom padding; the last element clears the tab bar by 39-51 px on every page measured. No change needed. | capture.py | none |
| F5 | high | **Budget: the plan is shown three times.** Categories (11 rows with meters), then Your plan (3 figures), then Spending by group (Personal, System Categories) with meters again. **Held.** Expected: the ring hero, the over-plan strip, then **one** list: over plan first, ahead of pace next, then "8 on track" as one row that opens the rest. Your plan becomes one quiet line under the hero ("Planned 25,599 · leaves 19,401 to save"). Spending by group leaves the phone page. | [2-budget.png](evidence/2-budget.png) | IV-3AL2 |
| F6 | medium | **Budget: limits are typed inside the list.** Opening a group shows rows with a live input each; a tap meant to open a category can land in a field and raise the keyboard. Owner's claim **partly held**: the inputs show only inside an opened group, not on every row. Expected: a category row opens a sheet with spent of limit, the limit field, Cover it and See transactions; the list has no fields. | `phone/budget.html` | IV-3AL2 |
| F7 | low | **Budget: "System Categories"** shows as a group name on the phone. The PC replaced it with what it holds (feedback ticket 93, `routes/budget.py` `note`); the phone template never reads `row.note`. | [2-budget.png](evidence/2-budget.png) | IV-3AL2 |
| F8 | low | **Budget: blocks before the list.** Owner's claim of "two screens before the limits" **partly held**: on the sample the list starts at 370 px; Bulk undo, Your income went up and Set your first limits add up to a screen only when they show. They should share the Needs you strip's place, one at a time. | [2-budget.png](evidence/2-budget.png) | IV-3AL2 |
| F9 | high | **Add asks which account first**, listing six with the rare ones (NBE CDs, THNDR brokerage, Bought in instalments) beside the daily ones. **Held.** Expected (3AD): amount first with Out / In / Transfer, the last-used account as a chip already chosen, category chips (usual first), and Save pinned above the keyboard. | [3-add.png](evidence/3-add.png) | NF-3AD (dated note added) |
| F10 | high | **Transactions opens on All time.** With no query the register shows every year: no ‹ › stepper, and Money in +138,667 / Money out −74,187 are lifetime totals that answer nothing (`routes/register.py`, empty `preset`). C08.3 shows the month. Same on an account's page. | [4-transactions-first-screen.png](evidence/4-transactions-first-screen.png) | IV-3AL3 |
| F11 | medium | **Transactions: 390 px of controls before the first row** (search, five chips, period + Select + ⋯, two tiles, Views + Show value updates). **Held.** Expected: search; the chip row; the stepper with Select and ⋯; Money in and out as **one line** ("In +… · Out −…"); Views and value updates move into ⋯. The first row then starts near 300 px. | [4-transactions-first-screen.png](evidence/4-transactions-first-screen.png) | IV-3AL3, owner D2 |
| F12 | low | **Transactions: each day's net repeats the row.** Most days hold one payment, so "2026-10-25 −2,000" sits over "Mom −2,000": every figure twice. Owner's "dense rows with flags" **not reproduced**: rows show name, category · account and amount only. Expected: the day's net only on a day with two or more rows. | [4-transactions-first-screen.png](evidence/4-transactions-first-screen.png) | IV-3AL3 |
| F13 | medium | **More opens on a card of three Mark paid buttons** (C12: a card around rows; C05.3: one action per row, in its sheet). Sections, the review and settings follow as one long list with subtitles. Owner's claim **held**. Expected, flat with three headings: *Due soon* (rows; a tap opens the pay sheet), *Your money* (Cash planning, Accounts, Investments, Financial health, Spending, each with its figure), the Weekly review card, then *Settings* as plain names with no subtitles. | [5-more.png](evidence/5-more.png) | IV-3AL4, owner D3 |
| F14 | low | **More: "0 due before payday" while it lists 14,850 due two to eight days after payday.** True, but reads as nothing to pay. Expected: "Next: Landlord 12,000 on 2026-11-03" when nothing falls before payday (the same on the Cash planning hero, F15). | [5-more.png](evidence/5-more.png) | IV-3AL4 |

### Pages reached from More

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F15 | medium | **Cash planning leads with "0 EGP".** Then Coming up, two tiles, a Safe to spend card with its working, a forecast chart (legend above it, C07), Each month ahead and What is promised: 2.8 screens. Expected: the hero says what is next when nothing falls before payday; Coming up with Mark paid stays first; the forecast, months ahead and What is promised become rows that open sheets. | [6-cash-planning.png](evidence/6-cash-planning.png) | IV-3AL5 |
| F16 | medium | **Recurring opens on a Primary "Add recurring item" above the tabs**, then "Fixed costs to income 35.5%" (Financial health's figure: A16 one figure, one home), then bills in a card with bars and ".00" on every row (C12). Expected: list first, Add as the page's Secondary under the tabs, the ratio a link to its home. | [12-recurring.png](evidence/12-recurring.png) | IV-3AL5 |
| F17 | medium | **Reserves sits under "Cash planning" with Financial health's tabs** (Reserves · Limits), "Emergency fund covers 0." is cut (C12; 3T item 1, still open) and Refill sits in a card in a card. Expected: the app bar names Financial health; one card. | [11-reserves.png](evidence/11-reserves.png) | IV-3AL5, IV-3T |
| F18 | medium | **Investments puts a chart before the holdings.** Hero, four tabs, stepper, value chart with Month/YTD/All, Return, then holdings; Allocation, income and horizon below; "Set a holding's horizon on the PC's Holdings table for now" is a dead end in desktop words (C12). Expected: hero, then the five biggest holdings with See all; the chart one row ("Over time ›"); horizon set on the phone or the row removed. | [7-investments.png](evidence/7-investments.png) | IV-3AL5 |
| F19 | low | **Accounts is the model**: hero, one Secondary (From SMS) with ⋯, then flat rows by group, 1.2 screens. Only the tab order is off: Import · **Accounts** · Held for others puts the daily tab in the middle. Expected: Accounts first. | [13-accounts.png](evidence/13-accounts.png) | IV-3AL5 |
| F20 | medium | **Financial health shows the problem third.** "5 of the 6 within your limits" with a savings-rate chart in the same card, then the rose "Emergency fund is outside your limit". No hero figure; the title wraps. Expected: the one thing that needs you as the lead with its action, then the six limits as rows; the chart one tap away. | [8-financial-health.png](evidence/8-financial-health.png) | IV-3AL5 |
| F21 | high | **Spending (More › Spending) is the PC report:** 6.1 screens, 71 figures, 14 small targets: KPI rows, a block chart, small multiples, "Now against your usual month", a calendar heat map, two money-flow diagrams and a month grid. The opposite of quick information. Expected: the lead (spent this month and against the same days usually), the four biggest categories then Other as rows, and one row "More analysis ›" that opens the rest (or Compare periods and Reports). | [9-spending.png](evidence/9-spending.png) | IV-3AL6 |
| F22 | medium | **Weekly review marks Overview in the tab bar** although it is reached from More (C03.1); a lone "Overview" tab chip; each decision's title repeats in its own row (A16); "Review" is cut to "Revi / ew" (C12); a checkbox before Record. Expected: More chosen, one decision at a time as its card says, no repeated title, one Primary. | [10-weekly-review.png](evidence/10-weekly-review.png) | IV-3AL7 |
| F23 | - | Settings' five wrapping tabs and missing ‹, the Prices page's "yyyy-mm-dd" and small targets are already filed in IV-3T (items 3, 6, 7, 13). Still present; not filed again. | capture.py | IV-3T |

### Owner decisions (the breakdown asks for something Part C forbids)

Part C is strict and lands in both repos, so these wait for the owner before building:

- **D1 Folds or sheets (C06.2).** Part C says "a row with › opens its parts in place". The breakdown asks for rows that
  open sheets. **Recommend sheets** for Overview's This period and Your position: one level, the page stays short, the
  sheet frame (C09) already exists.
- **D2 Transactions header (C08.3).** The breakdown asks for search plus one Filter button with a badge, and a slim
  money strip. **Recommend** keeping the chip row (each chip is a one-tap quick action and fits one line at 360) and
  taking the slim strip: C08.3's "two tiles, Money in and Money out" becomes one line.
- **D3 More as grouped inset cards.** C01.1 says "flat, not boxed" and C12 forbids a card around rows. **Recommend**
  flat rows under three headings (F13), which groups them without boxes. The Weekly review keeps its accent card.
- **D4 Month stepper at the top.** The breakdown moves it under the app bar. Part C already puts it right after the
  hero; the jump the breakdown saw comes from the due-payments card above it (F1). **Recommend** no guideline change.

## Validation and limits

Browser evidence only (Chromium with touch, 360 × 800, English, light theme, sample household). Not checked: Arabic,
dark and paid themes, 320 px, a real phone's keyboard (F9's Save above the keyboard), the Android shell. No code was
changed; `tools/phone_check.py` was not re-run. Figures counted by a pattern, so they are approximate.

## Dated follow-ups

- **2026-10-29, built on `claude/phone-declutter`** (owner: "Start fixing"): F1, F2 (one Needs you strip with Manage
  Needs you inside it), F5, F7 (Budget lists each category once; the plan's figures and the groups are under Edit plan,
  where Adjust and Change the plan now land), F10 (Transactions opens on this month; an account keeps its statement),
  F13, F14 (More flat with headings; a bill's row opens its pay sheet), F22. Tests: `tests/test_phone_frame.py`
  (`test_one_needs_you_strip_under_the_stepper_holds_what_is_due_tomorrow`,
  `test_more_is_flat_and_the_weekly_review_keeps_more_chosen`), `test_phone_budget.py`, `test_phone_transactions.py`.
  After: Budget 1.1 screens (was 2.6); Transactions' tiles show this month (+46,833 / −24,290), not the lifetime. The rest stays in IV-3AL.
- **2026-10-29, step 2** (owner: "Do as you deem fit and merge"; step 1 merged as #201): D1-D3 decided as recommended
  and recorded in the Project Overview. Built: F14/F15 (the Cash planning hero names the next payment), F16 (Recurring's
  page action is a Secondary on the phone), F18 (the horizon note points to the holding's page; the chart stays before
  holdings, the owner's PDF order, so that part of F18 is withdrawn), F20 (what needs you sits under the lead; the
  chart has its own card). D1 and D2 wait for a session that can change the website repo's guideline copy too.
