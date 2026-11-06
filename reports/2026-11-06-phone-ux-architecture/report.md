# The phone, redesigned: a phone-first architecture, tab by tab

Date: 2026-11-06 · Author/reviewer: Claude (UX design review)
Repository: app · Reviewed commit: 4af457b27dfe5ac15d05e518c624f928f1eb22fc

## Assessment

The owner (2026-11-06), with three screenshots of the Android app: "The phone UI is not usable. I want a full
architecture design, tab by tab, on how to make it usable. Do it as a UX designer and think of the user journey. Phone is
decoupled from PC."

Audits 10 and 13 fixed each phone screen in turn, and the five quick jobs now take three taps or fewer. The phone is still
not usable, because the problem is the **structure** behind the screens, not any one screen:

1. **The phone is a PC dashboard turned into one long column.** Overview carries 22 figures over 2.3 screens: Safe to
   spend, Net worth twice, Your position, This period and six analysis rows. More is a second dashboard.
2. **One question gets four different answers.** "What bills do I owe?" shows 17 (Needs you), 7 (Bills due to pay),
   13 (Next 14 days) and 11,760 due before payday on the same day. "How much money do I have?" shows 1,051,102,
   988,804 and 236,317 with no word on how they differ.
3. **Nothing on the phone knows what state the person is in.** A week without recording, payday, a month overspent and a
   first launch all get the same layout. A week away turns into a wall of red "34 days late" rows.
4. **The code ties the phone to the PC.** Each phone page runs the PC's route and then picks a phone template, if one
   exists. 78 of the 104 page templates have no phone version, so the phone shows the PC's markup. The phone CSS is
   1,029 lines of overrides on top of the PC stylesheet.

**The answer** is a phone built as its own product. It shares the PC's services, figure names, brand tokens and
profile, and nothing else. It has five places, and each answers one question for one moment:

| Slot | Question it answers | Replaces |
| --- | --- | --- |
| **Home** | Am I OK today, and what do I do next? | Overview |
| **Budget** | How much is left to spend, and on what? | Budget |
| **Add** | Record it now | Add |
| **Activity** | What moved, and what needs sorting? | Transactions, the sorting half of Needs you |
| **Money** | What do I have and owe, and what is coming? | More, Your position, Accounts, Cash planning's bills |

Settings goes behind a gear on Money. Analysis stays on the PC, or one tap deep. Home has no month stepper: it is always
today.

## Scope and method

- **The owner's screenshots:** an Android phone (about 412 px wide) on 2026-11-06, showing More and two parts of
  Overview. The household is a bigger sample whose entries end on 2026-10-31. It was opened six days later, which is
  exactly what a person sees after a week without recording. The screenshots are not committed: a video overlay in them
  shows a third party. Each finding below says what they show.
- **The capture:** the phone app (`profile_app(..., phone=True)`) on the `/demo` household, in Chromium with touch at
  412 × 915, on 2026-11-06. It covered 15 pages, Overview on this month and on last month included
  ([evidence/capture.py](evidence/capture.py), output [evidence/metrics.json](evidence/metrics.json); the six shots used
  here were renamed `1-` to `6-`).
- **The code:** the routes and templates that build the phone (`lightning/ui/web.py` `_phone_template`,
  `routes/dashboard.py`, `templates/phone/`, `static/phone.css`).
- **The rules:** guideline Part C (C01 to C12) and A16. Audits 10 and 13, issue 3AN and the 2026-11-05 desktop/phone
  report were read so this design builds on them and does not repeat them.
- **The method:** the persona and moments come from the Project Overview's Mohab and the earlier audits. Each tab is
  designed for its moment (what the person wants, where they are, how long they have). After that come its first
  screen, its states, what leaves it, and how it is measured.

| Page today (demo sample, 412 × 915) | Screens long | Figures | Targets |
| --- | --- | --- | --- |
| Overview, this month | 2.3 | 22 | 67 |
| Overview, last month (stepper ‹) | 2.2 | 18 | 63 |
| Budget | 1.6 | 6 | 35 |
| Transactions | 1.3 | 12 | 33 |
| More | 1.4 | 4 | 16 |
| Needs you | 1.0 | 1 | 29 (four buttons per item) |
| Cash planning | 1.9 | 15 | 22 |
| Investments | 2.6 | 30 | 23 |
| Financial health | 2.5 | 9 | 25 |
| Settings | 3.6 | 0 | 45 |
| An account | 5.6 | 92 | 82 |

## Findings

Severity: **high**: the person cannot get their answer or gets a wrong or conflicting one. **Medium**: daily friction.
**Low**: polish.

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | high | **Four counts for one question.** On one day the bills appear as Needs you 17, Your position › Bills due to pay 7, More › Next 14 days 5 + "8 more", and Cash planning "11,760 due before payday". Each is built by its own query with its own window (`_due_soon` 3 days, `more()` 14 days, `owe.bills_due_items`, the forecast). Expected: one bill state, worked out once in Python (late, due soon, before payday, later), with every surface reading it. | owner shots 1, 3; `routes/dashboard.py` `_due_soon`, `more` | 3AY5 |
| F2 | high | **A week away becomes a wall of red.** Under the heading "Next 14 days", the first five rows are 34, 32, 28, 25 and 17 days *late*, then "8 more". The person cannot tell whether they forgot to pay or forgot to record, and there is no way to clear them all. Expected: bills late by more than 7 days, or from before the last payday, fold into one question, "5 bills from October: did you pay them?", with *All paid*, *Not yet* and per-row answers. "Next 14 days" lists only what is coming. | owner shot 1 | 3AY1, 3AY5 |
| F3 | high | **Home changes meaning when the month changes.** With the stepper on 2026-10, the Safe to spend hero becomes Net worth, the tile beside it repeats the same Net worth (908,344 twice), the tile still says "Today" over a 2026-10-31 figure, Latest still lists November, and Needs you loses its summary line. Expected: Home is always today and has no stepper. Months belong to Budget and Activity. | owner shot 2; [2-home-last-month.png](evidence/2-home-last-month.png); `_worth_tile` | 3AY1, 3AY6 |
| F4 | high | **Overview is a report.** It has 22 figures, 67 targets and 2.3 screens: Your position (8 rows, two of them in dollars and in gold), This period (6 rows) and analysis sheets. Moment by moment, the phone needs one figure (Safe to spend), the next thing to do, and the latest money. | [1-home-today.png](evidence/1-home-today.png) | 3AY6 |
| F5 | high | **"How much do I have?" has three answers with no reconciliation.** More › Accounts 1,051,102, What you own 988,804, Cash you own 236,317 (owner); 261,671, 265,671 and 87,768 on the demo. Only the Accounts page explains the difference. Expected: Money leads with one figure (Net worth, or What you own with no debt). Accounts list balances under it, and a row says how the two differ when they do. | owner shots 1, 3; [3-more.png](evidence/3-more.png) | 3AY10 |
| F6 | medium | **Needs you is a to-do list without the doing.** The card says "17 items need you" and then shows the badge 17 again. Opened, each item has four buttons (Review, Match, Mark as reviewed, Snooze: 29 targets for 4 items). It mixes bills, uncategorised rows, deposit interest, an emergency-fund warning and "Salary received". Expected: Home shows **To do**: the top three items, each with its one action, then *See all*. Sorting goes to Activity › To review, one card at a time. Bills go to Money › Bills. | [5-needs-you.png](evidence/5-needs-you.png) | 3AY6, 3AY8 |
| F7 | medium | **"329 new transactions since your last visit on 2026-11-06"**: the last visit is today, and the 329 rows were one sample load. Expected: a bulk import or sample is one event ("329 imported from the sample"), and the line never names today as "your last visit". On Home, To review's count replaces this line. | owner shot 2; `routes/dashboard.py` `since` | 3AY1 |
| F8 | medium | **Budget mixes setting up with checking.** With no plan for the month, the page opens on 2026-10 with an 11-category form, then lists categories at "0 left" (rent, loan, bills). Fixed bills count as spending against the pace (2026-11-05 report F5). Expected: one *Make my plan* step that proposes limits; flexible spending and fixed costs are kept apart, so "left" means money you can still choose to spend. | [4-budget.png](evidence/4-budget.png) | 3AY9 |
| F9 | medium | **More is a junk drawer.** It holds bills, six sections with figures, the weekly review card and six settings rows, with no question it answers. Expected: Money (what you have, owe and what is coming), with Settings behind a gear. | [3-more.png](evidence/3-more.png) | 3AY10 |
| F10 | medium | **The phone renders PC pages.** `_phone_template` falls back to the PC template when there is no phone one: 78 of 104 page templates, Financial health, Needs you, Settings, a holding, a transaction, Categories, Rules, Reserves and Loans among them. The PC routes carry phone switches in 12 files (`on_phone`, `lazy_folds`). The Overview route also computes investment periods, a wealth donut, net-worth bridges and month calendars for the phone. Expected: a phone router with its own screens, and no PC fallback (see Technical architecture). | `lightning/ui/web.py`; `templates/` | 3AY4, 3AY11 |
| F11 | low | **"Net worth · in us dollars"**: the template lower-cases the whole label (`('In ' ~ u.unit)\|tr(locale)\|lower`), so "US" becomes "us". "at 52 on 2026-09-30" does not say 52 of what. Expected: "In US dollars", with "1 USD = 52 EGP on 2026-09-30" under it, and only on Money. | owner shot 3; `phone/dashboard/index.html` | 3AY1 |
| F12 | low | **Figures move around within a list.** A row with › puts its figure in the middle column; a row without › puts it at the right edge. "What you owe" is bold while its siblings are regular. Expected: figures always end at the right edge, with › outside the figure column (C08). | owner shot 3 | 3AY4 |
| F13 | low | **The clock cannot be seen.** In the Android shell the status bar draws white icons on the light app bar, so the time and battery disappear. Expected: dark status-bar icons on light themes, light icons on dark themes, set from the theme. | owner shots | 3AY4 (with IV-3F) |

## Who the phone is for, and when

**Mohab** (the acceptance persona, `tests/test_mohab_year.py`): 31, salaried in Cairo, paid on the 1st, one payroll
account, a cash wallet, a card, a car loan, a gam'eya and some certificates. He sits down at the PC to set up, import a
statement or think about investments. The **phone** comes out for short moments, with one hand, often standing up:

| # | Moment | How often | What he wants in that moment | Today | Target |
| --- | --- | --- | --- | --- | --- |
| J1 | Just paid cash at a kiosk | several a day | Record it before he forgets | 3 taps | 3 taps, and the category's "left" shown on save |
| J2 | A bank SMS arrived | daily | Turn it into a transaction | 2 taps | 2 taps |
| J3 | "Can I afford this?" | daily | One number he can trust | 0 taps, only while the month is today | 0 taps, always; 1 tap to check an amount |
| J4 | "How much is left for eating out?" | weekly | Left in that category | 1 tap | 1 tap |
| J5 | A bill is due | monthly per bill | Pay it or mark it paid | 2 taps | 2 taps |
| J6 | Friday catch-up | weekly | Clear what is unsorted, fast | 4 buttons per item | 1 tap per item, one card at a time |
| J7 | Salary arrived | monthly | Give the salary its jobs | a page from Needs you | a guided 3-step flow from Home |
| J8 | "What's in CIB?" | weekly | One balance | 2 taps (More › Accounts) | 1 tap (Money) |
| J9 | Back after a week away | monthly | Catch up without shame | a wall of red | one catch-up flow, about 2 minutes |
| J10 | "Where did I pay that?" | weekly | Find a payment | 1 tap to search | 1 tap to search |

Design rule from the table: **the moments that happen daily get zero or one tap from Home. Weekly moments get one
place. Monthly moments are triggered by state (payday, a bill, being away), so the phone brings them up and the person
does not have to go looking.**

## Principles for every phone screen

1. **One question per place.** Each slot answers the question in the table above; if a block does not help answer
   it, it moves to its own place.
2. **Today by default.** Home and Money are always today. Months belong to Budget and Activity, which look back.
3. **One count per concept.** A bill, a sum or an item has one number everywhere it appears, from one Python
   service.
4. **Do, don't just tell.** Every alert carries its one action (Pay, Sort, Plan). Never a count without a way to clear
   it.
5. **State-aware.** First run, catch-up, payday, overspent and calm are different screens, not the same screen with
   different numbers.
6. **One level deep.** A list row opens a sheet (the details and one action) or a page (a longer list). Never a fold
   inside a fold, never a PC page.
7. **Thumb first.** The action sits at the bottom or in the row. Add is always the middle slot. Save stays above the
   keyboard.
8. **Analysis is optional.** Charts and breakdowns sit one tap away on the phone or on the PC. They never sit in a
   list the person scrolls every day.

## Information architecture

```
Home ─────────── Safe to spend · To do (3) · Latest (5) · This month (1 row)
 ├ To do › all ─ every action waiting, grouped by place
 ├ Catch-up ──── flow: missed bills · paste SMS · import a statement      (state: away ≥ 3 days)
 └ Payday ────── flow: salary arrived › fixed costs › flexible plan › savings (state: income received)
Budget ───────── Left in plan · needs attention · flexible categories · Fixed costs (1 row)
 ├ Category ──── sheet: spent of limit, pace, latest 5, Move money, Change limit
 └ Make my plan  flow (state: no plan this month)
Add (sheet) ──── amount › Out / In / Move › account chip › category chips › Save
 └ Paste SMS · Pay a bill (chips at the top of the sheet)
Activity ─────── [All | To review n] · search · chips · month ‹ › · day groups
 ├ Transaction ─ sheet: category chips, note, split, rule, delete
 └ To review ─── one card at a time: confirm, change, skip
Money ────────── Net worth · Accounts · Coming up · What you owe · Investments · Goals & reserves · Health
 ├ Account ───── page: balance, Check against the bank, this month's rows
 ├ Bills ─────── page: late (as one question) · this week · before payday · after payday · Recurring
 ├ Investments ─ page: value, holdings, prices to update; chart one row deep
 ├ Financial health, Zakat (when on)
 └ ⚙ Settings ── grouped rows; PC-only tools say so
```

**Where today's pages go**

| Today | Goes to |
| --- | --- |
| Overview hero, Needs you card, Latest | Home |
| Overview › Your position, Net worth in USD and gold | Money (hero, then a sheet) |
| Overview › This period, month charts | Budget › *This month in detail* sheet, or the PC |
| Needs you page | Home › To do (actions), Activity › To review (sorting), Money › Bills |
| More › Next 14 days, Cash planning | Money › Coming up and Bills; Safe to spend's working is a sheet from Home's hero |
| More › sections | Money rows |
| More › Weekly review card | Home To do, on its day ("Your weekly check · 4 decisions") |
| More › Settings rows | Money › ⚙ Settings |
| Spending (birdview) | Budget › *This month in detail* (the four biggest, then Other) |

## Tab by tab

Wireframes are at 412 × 915: the app bar takes 56 px, the tab bar 72 px, and the first screen holds about 700 px. Each
tab names its **job**, its **first screen**, its **states**, its **actions**, what **leaves** it, and how it is
**measured**.

### 1. Home: "Am I OK today, and what do I do next?"

**Job.** The 3-second glance (J3) and the start of every other moment. It opens in under a second, and the person can
leave as soon as they have read the hero.

```
┌───────────────────────────────────────────┐
│ ⚡ Home                           🔍   👁  │
├───────────────────────────────────────────┤
│ Safe to spend                             │
│ 51,420 EGP                                │
│ About 2,057 a day until payday, 2026-12-01│
│ ▔▔▔ (seam)                                │
│ To do                                  5  │
│  Vodafone 350 · in 3 days          Pay ›  │
│  12 new transactions to sort      Sort ›  │
│  Salary arrived · 45,000          Plan ›  │
│  See all 5                                │
│ Latest                          See all   │
│  Today                                    │
│  ↓ Carrefour  Groceries          −3,410   │
│  … five rows                              │
│ This month                                │
│  Spent 18,651 · Left in plan 6,948     ›  │
└───────────────────────────────────────────┘
```

- **Hero:** Safe to spend, always today. Tapping it opens a sheet with its working (free cash, minus bills before
  payday, minus reserves), which today lives on Cash planning (2026-11-05 report F11). Below zero, it turns rose:
  "You are 1,200 over until payday", with *See why* opening the same sheet.
- **To do:** at most three rows, picked in this order: a late or due-today bill, payday, catch-up, to sort, the
  weekly check, prices, then the rest. Each row is a sentence with **one** action on the right, and the action does the
  job in a sheet or flow. *See all* opens the full list, grouped by place. With nothing waiting, the section is gone
  (A09).
- **Latest:** the five newest transactions across accounts. The day header shows only when the day changes; a row tap
  opens its sheet.
- **This month:** one row with two figures. It opens Budget.
- **Leaves Home:** the month stepper, Net worth (both copies), Your position, This period, the analysis sheets, Get set
  up (it becomes the first-run state) and the "since your last visit" line.

**States.**

| State | When | Home shows |
| --- | --- | --- |
| First run | no account or no income yet | Three steps as the whole page: *Your salary account*, *Your payday*, *Your first payment*. The hero waits until they are done. |
| Catch-up | nothing recorded for 3+ days, or bills late more than 7 days | A **Catch up** card above To do: "Nothing recorded since 2026-10-31. Two minutes to catch up." It opens a flow: missed bills (paid / not yet), *Paste SMS*, *Import a statement*, *Later*. The hero says "May be off: 6 days not recorded". |
| Payday | income arrived today or yesterday | "Salary arrived · 45,000 · Plan it ›" is To do's first row and opens the payday flow. |
| Overspent | Safe to spend below zero | Rose hero, *See why*. The first To do row is the biggest flexible category over its limit. |
| Calm | none of the above | Hero, Latest, This month. To do is gone. |

**Measured:** one screen, at most 1.2 screens long; at most 8 figures; the first Latest row above 600 px; zero taps for
J3.

### 2. Budget: "How much is left, and on what?"

**Job.** J4, plus the weekly look back. This is where months live.

```
┌───────────────────────────────────────────┐
│ ⚡ Budget                         🔍   👁  │
│ Left in plan            ◔ 73% used        │
│ 6,948 EGP                                 │
│ 532 under your pace for 2026-11.          │
│ ‹ 2026-11 ›                               │
│ Needs attention                           │
│  Eating out    ███████▉ 1,950 of 2,000  50│
│  Transport     ██████▌  1,400 of 1,800 400│
│ Your categories                           │
│  Groceries     ████▏    2,100 of 5,000 2,900
│  … sorted by what is left, smallest first │
│ Fixed costs        16,000 of 16,000 paid ›│
│ This month in detail                    › │
└───────────────────────────────────────────┘
```

- **Hero:** Left in plan, counting **flexible spending only**, with the ring; the sentence compares it to the pace.
- **Needs attention:** categories over their limit, or ahead of the month's pace. At most four, then "and 2 more".
- **Your categories:** every flexible category, one row each, with a thin bar on the right and **left** as the figure.
  The list has no fields in it.
- **Fixed costs:** rent, loans, subscriptions and bills as **one** row ("16,000 of 16,000 paid"). It opens Money ›
  Bills. They no longer drag the pace or show as "0 left".
- **Category sheet:** spent of limit, pace ("on day 6 you usually spend 1,200"), the latest five, then *Move money
  here*, *Change limit* and *See all transactions*.
- **This month in detail:** a page with the four biggest categories and Other, against the same days usually, plus net
  flow. The rest of Spending's analysis stays on the PC.

**States.** *No plan this month*: the page is the **Make my plan** step. One sentence, the proposed limits (round, from
3AH/BU-3), each editable in its sheet, and *Save plan*. Nothing else shows until it is saved. *Payday*: a strip at the
top, "Plan this month's 45,000 ›", opens the payday flow. *A past month*: no Needs attention section, and the hero says
how the month ended.

**Measured:** the first category row above 400 px; one tap to any category's left (J4); no input on the list.

### 3. Add (the middle slot): "Record it now"

**Job.** J1 and J2. It opens as a sheet over whatever tab is open and returns there.

```
┌───────────────────────────────────────────┐
│  [Paste SMS]  [Pay a bill]                │
│  Out  ·  In  ·  Move                      │
│              350                     EGP  │
│  From  (Cash wallet ▾)    Today ▾         │
│  [Groceries] [Transport] [Eating out] [+] │
│  Payee (optional)                         │
│ ───────────────────────────────────────── │
│ [            Save            ]            │ ← above the keyboard
│  1  2  3                                  │
└───────────────────────────────────────────┘
```

- The amount comes first, with the number keyboard up. The account chip is the last one used. The category chips are
  the six this person uses most at this time of day. The date chip says Today.
- **After Save:** a toast, "Saved · Groceries −350 · 2,550 left · Undo". The person sees the budget effect without
  opening Budget.
- **Paste SMS** reads the clipboard; several messages become a short list to confirm. **Pay a bill** lists what is due
  and opens its pay sheet. One place covers every way money moves.
- **Leaves Add:** the "which account?" list (already gone in 3AN), and any field that is rare (tags, split, notes go
  in the transaction's sheet after Save).

**Measured:** J1 in 3 taps (Add, a chip, Save) with the amount typed; Save visible with the keyboard open at 320 px.

### 4. Activity: "What moved, and what needs sorting?"

**Job.** J6 and J10. It is the ledger, and the one place where sorting happens.

```
┌───────────────────────────────────────────┐
│ ⚡ Activity                       🔍   👁  │
│ [ All ] [ To review 12 ]                  │
│ 🔍 Search payments                        │
│ (Out) (In) (Transfers) (Account ▾)        │
│ ‹ 2026-11 ›     In +46,833 · Out −18,651  │
│ Yesterday                                 │
│  ⇄ CIB → Office gam'eya          2,000    │
│  ↓ Toyota Finance  Loan payments −2,500   │
│ 2026-11-04                                │
│  ↓ Fitness Time Gym  Health        −900   │
└───────────────────────────────────────────┘
```

- **All:** the month's rows, newest first, with money in and out on one line. A day's net shows only when the day has
  two or more rows. A row opens its sheet: category chips (one tap changes it), note, split, *Always this category for
  this payee* (a rule) and delete. A long press starts selecting.
- **To review:** one card at a time, with a progress line ("3 of 12"). Each card holds the row, its source (SMS, a
  statement, the sample) and the suggested category as chips. **Looks right** is the Primary; *Change* and *Skip* sit
  beside it. The queue holds uncategorised rows, SMS to confirm, possible duplicates, interest to match on a
  deposit and "looks recurring → track it?". Each kind keeps its own one action. The queue ends on "All sorted", and
  that clears the To do row on Home.
- **Search** is live, payments first (as 3AN built it).
- **Leaves Activity:** Views and value updates (behind ⋯), the PC's table controls.

**Measured:** the first row above 330 px; one tap per reviewed item; 12 items sorted in under a minute on the demo.

### 5. Money: "What do I have, what do I owe, what is coming?"

**Job.** J5, J8 and the weekly "where do we stand". It replaces More.

```
┌───────────────────────────────────────────┐
│ ⚡ Money                       🔍  👁  ⚙  │
│ Net worth                                 │
│ 199,171 EGP                               │
│ +36,745 since 2026-11-01.                 │
│ Accounts                       261,671    │
│  CIB Payroll                    84,393    │
│  Cash wallet                    10,475    │
│  NBE certificates              100,000    │
│  Gold at home                   57,195    │
│  3 more                               ›   │
│ Coming up                     All bills › │
│  Vodafone  in 3 days               350    │
│  WE Internet  2026-11-20           650    │
│ What you owe                    66,500 ›  │
│ Investments                    177,903 ›  │
│ Goals and reserves      Emergency 0.8 mo ›│
│ Financial health      4 of 6 within limits›│
└───────────────────────────────────────────┘
```

- **Hero:** Net worth (What you own when nothing is owed), always today, compared with the start of the month. A tap
  opens a sheet: what you own, cash, holdings and what you owe, over time, and in US dollars and in 21K gold.
- **Accounts:** the balances themselves, four then "N more", so J8 is one tap from any tab. When Accounts' total
  differs from what you own, one quiet line says why ("includes 10,000 held for others").
- **Coming up:** the next three bills, **never** late ones. Late bills are a single To do row on Home and the first
  block on the Bills page. A row opens its pay sheet (J5).
- **Bills page:** *Late* as one question with *All paid / Not yet* (F2), then This week, Before payday, After payday
  and Recurring (manage). This takes over Cash planning's bill list. The forecast chart stays on the PC.
- **Investments page:** portfolio value with change, the holdings (five, then all), and "2 prices to update" when there
  are some. The value chart is one row ("Over time ›").
- **An account:** its balance, **Check against the bank** ("Does CIB say 84,393?" → *Yes* / *Fix it*), then this
  month's rows. Rare actions go behind ⋯.
- **⚙ Settings:** grouped rows (Appearance and language, This phone, Your data, Categories and rules, Devices).
  Tools that are only practical on the PC (Data checks, imports mapping, price files) are marked "Best on your PC" and
  never render the PC page on the phone.

**Measured:** one tap to any balance; bills counted once (the Bills page, Coming up and Home's To do agree); no late
row under "Coming up".

## Cross-cutting systems

1. **The bill state, once.** A Python service gives each payment one state for a day: *late and stale* (late more than
   7 days, or due before the last payday), *late*, *due soon* (3 days), *before payday*, *later*, *paid* or *skipped*.
   Home's To do, Money's Coming up, the Bills page, Safe to spend and the PC all read it. A test proves the four
   surfaces agree on Mohab's year (F1).
2. **Catch-up.** The away state is designed, not left to emerge from the data. It needs "days since the last entry"
   from the ledger, the late-and-stale bills, and the SMS waiting. One flow clears them in that order. A bulk import or
   a sample load is recorded as one event, so "new since" stops counting it as 329 surprises (F7).
3. **To do and To review.** To do is Home's prioritised list of **actions** (at most three shown). To review is
   Activity's queue of **rows to confirm**. Needs you's page becomes To do's *See all*. "Mark as reviewed" and "Snooze"
   collapse into one *Not now*, which moves the item down for a week.
4. **Time.** Home and Money are today. Budget and Activity have the stepper, and its sheet offers This month, Last month
   and Custom. Changing the month never changes what a figure means.
5. **Navigation.** Each slot keeps its own stack. Tapping the chosen slot again returns to its top. Android's back
   gesture pops within the slot, then goes to Home, then leaves. Lists are pages; details and actions are sheets
   (half height, drag to full). Add returns to the slot it was opened from.
6. **Words and numbers.** Glossary names unchanged (Safe to spend, Left in plan, Net worth, What you own). Figures
   always end at the right edge and the chevron sits outside them (F12). No label is lower-cased by code (F11). Whole
   EGP. Dates as yyyy-mm-dd (A06.1), or Today / Yesterday / in 3 days.
7. **The shell.** The status bar icons follow the theme (F13). Safe areas are taken from the window insets. The
   tab bar sits above the gesture bar.
8. **Arabic and themes.** Every new string goes into the catalogue in the same change (skill `arabic-check`); layouts
   mirror; paid themes use the same tokens, so they need no phone-specific work.

## Technical architecture: decoupling the phone

**Today.** One URL, one route and one context serve both the PC and the phone. `_render` swaps in
`templates/phone/<name>` when it exists and otherwise renders the PC template inside the phone frame. The PC routes
check `request.state.phone` in 12 files to skip work or add phone data. The phone stylesheet bundle is `style.css`
followed by `phone.css` (1,029 lines of overrides), so a PC style change can break the phone.

**Target.** The phone is a separate presentation layer over the same services:

```
lightning/ui/phone/                 new package; may not import lightning.ui.routes (import-linter contract)
  router.py                         mounted only by profile_app(..., phone=True); owns every phone URL
  screens/home.py budget.py add.py activity.py money.py bills.py account.py investments.py settings.py
                                    each: build(c, day, params) -> a frozen dataclass with exactly what the screen shows
templates/phone/                    phone templates only, from phone/base.html; never extends a PC template
static/phone/phone.css              stands alone on the theme tokens (themes.generated.css), not layered on style.css
lightning/planning/bill_state.py    the one bill state (cross-cutting 1), used by PC and phone
lightning/workflows/todo.py         To do priority and To review queue, from the existing ReviewInbox
```

- **Screens compose; services calculate.** A screen module calls services and formats; any new figure (the bill
  state, flexible-only Left in plan, days since the last entry) is a service with its own test (AGENTS §4: money logic in
  Python services).
- **No PC fallback.** A URL the phone router does not own returns a phone page: "This is on your PC", with what it is
  and how to get there. A test fails if any phone route renders a template outside `templates/phone/`.
- **Each screen asks only for what it shows.** Home needs the forecast, To do, five rows and the month's spent and left,
  not investment periods, donuts and month calendars. The perf check (`tools/perf_check.py`) gets a query budget per
  phone screen.
- **URLs.** The phone owns `/`, `/budget`, `/activity`, `/money`, `/money/bills`, `/money/accounts/<id>` and so on.
  Old phone URLs (`/transactions`, `/more`, `/plan`, `/accounts`) redirect, so notifications, search results and
  journal links keep working.
- **Strangler migration.** The new router takes over one slot at a time. The PC routes lose their phone switches,
  and `phone/` templates that copy PC ones are deleted as each slot moves. At the end, `_phone_template` and
  `request.state.phone` checks are gone from `lightning/ui/routes/`.
- **Tests.** `tests/test_phone_screens.py` (each screen's dataclass on Mohab's year: one bill count across Home, Money
  and Bills; flexible Left in plan; the catch-up state on a stale profile); a template-ownership test; the existing
  `tools/phone_check.py` (no sideways scroll, 48 px targets) and `tests/test_phone_nav_browser.py`. Mohab gets the
  catch-up and payday journeys as steps.

## Guideline Part C changes this needs (owner; both repos)

The design keeps Part A's brand and A16, but it changes Part C in these places. Per AGENTS §1 the change lands in the app's
and the website's `guideline/` in one session, with a PR in each:

- **C01.1 "One organism"** becomes **"Same brand, own structure"**: the phone shares figure names, tokens, the mark, the
  arrows and the seam with the PC, but not its sections, order or pages (owner, 2026-11-06: "Phone is decoupled from
  PC").
- **C03.1 Tab bar:** Home, Budget, Add, Activity, Money; More is gone; Settings sits behind ⚙ on Money's app bar.
- **C04.2 Period:** the stepper only on Budget and Activity; Home and Money are today.
- **C04.4 Needs you** becomes Home's **To do** (at most three rows, one action each) and Activity's **To review**.
- **C11.1 Overview** becomes **Home**, and **C11.3 More** becomes **Money**, redrawn from the wireframes above.
- **New C13 States:** first run, catch-up, payday, overspent and calm, each with what the screen shows.

## Build plan

Plan item [IV-3AY](../../issues/3-polish-and-arabic/3AY-phone-first-architecture.md) holds the steps, in order. The
first one fixes today's four state and copy bugs (F3 tile, F7, F11 and the late rows under "Next 14 days") and can ship
before the owner's decisions. 3AN's remaining Accounts-tab-first step (3AN12) is overtaken by Money, and its owner check
(3AN13) joins 3AY's.

## Acceptance

The phone is usable when, on Mohab's year at 412 × 915 and at 320, in English and Arabic:

- J1 to J10 meet the targets in the table above (counted the way Audit 13 counted taps);
- Home fits in 1.2 screens with at most 8 figures, and Safe to spend shows in every month state;
- one bill count everywhere, on a profile left alone for a week (the owner's case) and on a fresh one;
- no phone URL renders a PC template; the PC routes have no phone switches;
- every A16 line holds, and `tools/phone_check.py` passes.

## Decisions for the owner

These wait for the owner, asked as a pick-list in the session. The safe step (3AY1) does not depend on them; the answers are recorded in 3AY2.

- **D1 Tab bar.** Recommended: Home · Budget · Add · Activity · Money (More becomes Money, Settings behind ⚙).
- **D2 Home without the month stepper and without Net worth.** Recommended: yes; Net worth leads Money.
- **D3 Late bills.** Recommended: late more than 7 days, or from before the last payday, becomes one catch-up question,
  never a list of red rows.
- **D4 Guideline Part C rewrite** (above), in both repos. Recommended: yes, before the screens are built.

## Validation and limits

Browser evidence on the demo household at 412 × 915, English, light theme. The owner's screenshots come from a real
Android phone running a larger sample whose entries end on 2026-10-31. Not checked here: Arabic, dark and paid themes,
320 px, the real keyboard, TalkBack. Tap targets and wireframes are design targets, not measurements of built screens.
Figures were counted with a pattern, so they are approximate. No app code was changed.

## Dated follow-ups

None yet.
