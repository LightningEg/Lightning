---
title: Phone visual plan - a thumb-first phone built for five quick jobs, each done in three taps or fewer
type: polish
pillar: everywhere
size: L
status: building
post: no
created: 2026-11-01
by: Claude
skills: guideline-audit, arabic-check
app_version: 1.5.4
commit: 4ba2732
repo: app
---

## Report
[Audit 13](../../reports/2026-11-01-phone-convenience-audit/report.md) (owner, 2026-11-01: "the flow, clutter and
visuals are not set for a phone user; audit the phone from UX and UI and build a visual plan only for the phone, based on
convenience and quick actions"). The phone ran on the sample household at 360 × 800 with touch, at 320, and in Arabic, on
the first day of a month. Screens are `evidence/NN-*.png` beside the report.

Audit 10 (IV-3AL, 2026-10-29) fixed the layout of each tab one by one. What is still wrong is mostly **between** the tabs:
the jobs a person opens the phone for take too many taps, the action sits far from the thumb, and the screens look boxed
and busy. This item is the plan for the whole phone. It does not repeat open work: it names the steps of IV-3AL, NF-3AD
and IV-3T where they already cover a point and puts every step in one order.

### Who opens the phone, and for what
A salaried person in Cairo opens Lightning on the phone for seconds, not minutes: at the till, after a bank SMS, on payday,
the day a bill is due, before buying something. The PC is for analysis. So the phone has five jobs:

| Job | Taps today (from Overview) | Target | What is in the way |
| --- | --- | --- | --- |
| **J1 Record a payment** | 6 and a scroll: Add, choose an account, amount, counterparty, Category, pick, scroll, Save | **3**: Add, amount, a category chip, Save | Asks the account first ([10](../../reports/2026-11-01-phone-convenience-audit/evidence/10-add-which-account.png)); Save is at 847 px on an 800 screen with no keyboard up ([11](../../reports/2026-11-01-phone-convenience-audit/evidence/11-add-entry-sheet.png)); categories are a picker, never chips |
| **J2 Turn a bank SMS into a transaction** | 3 from Add (Add, account, Paste bank SMS) or 2 from More (More › Settings › From SMS) | **2**: Add, Paste SMS | It sits under *Settings* on More; Add asks for an account the SMS already names; the SMS page has no way back and six lines of help ([16](../../reports/2026-11-01-phone-convenience-audit/evidence/16-from-sms.png)) |
| **J3 Pay the next bill** | 3: More, the bill, Mark paid. Overview shows a bill only when it is due today or tomorrow | **2** from Overview: the bill in Needs you, Mark paid | Landlord 12,000 in 2 days is on More and Cash planning, not on Overview |
| **J4 "How much is left for groceries?"** | 1 and a scan: nine rows in A-Z order, 90 px each, every meter empty on day one ([02](../../reports/2026-11-01-phone-convenience-audit/evidence/02-budget-full.png)) | **1**: the row is in the first screen, ordered by need | Tapping the row leaves Budget for Transactions on a "Custom range" that says "Nothing matches" ([17](../../reports/2026-11-01-phone-convenience-audit/evidence/17-budget-category.png)) |
| **J5 Find or fix a payment** | App-bar search finds pages, not money, and says "Press Ctrl K" ([15](../../reports/2026-11-01-phone-convenience-audit/evidence/15-search.png)); sorting one row is 6 taps (To sort, row, Category, pick, scroll, Save) | **1** to search (live, money first); **3** to sort, the next unsorted row opening by itself | Two searches with two jobs; a row opens the full edit form with Save off screen ([12](../../reports/2026-11-01-phone-convenience-audit/evidence/12-row-edit-sheet.png)) |

### Findings (new in this audit; P = phone plan)
Severity: **high** blocks a quick job; **medium** clutter seen daily; **low** polish.

| ID | Sev. | What is wrong | Evidence | Step |
| --- | --- | --- | --- | --- |
| P1 | high | **Overview's first screen has no money that moved.** Hero, a 200 px white stepper pill, Needs you, then four 150 px tiles; "Latest" starts at 682 px and its first row sits under the tab bar (735). C01.1 and C12 ask for the latest transactions right after the tiles, in view. | [01](../../reports/2026-11-01-phone-convenience-audit/evidence/01-overview.png) | 3AN4 |
| P2 | medium | **Two rate tiles say nothing on most days.** On the 1st: Savings rate **100.0%**, Investing rate **0.0%**, each with decimals and an empty meter. A month-to-date rate is noise until the month has run. | [01](../../reports/2026-11-01-phone-convenience-audit/evidence/01-overview.png) | 3AN0, 3AN4 |
| P3 | high | **Add: account first, Save out of reach** (NF-3AD F9, still open), and the sheet has its own look problems: a card inside the sheet (A16: card in a card), "0.00" in the amount, a picker for Category, a sentence in system words ("Cash in Cash wallet decreases by … EGP; balance owned by You."), and in Arabic that sentence is half English ("هتdecreases"). | [11](../../reports/2026-11-01-phone-convenience-audit/evidence/11-add-entry-sheet.png), [21](../../reports/2026-11-01-phone-convenience-audit/evidence/21-ar-entry-sheet.png) | 3AN1, 3AN3 |
| P4 | high | **A row opens the full edit form**: "45,000.00", every field open, Save and Delete off screen. A tap meant to look becomes an edit. NF-3AD2 plans the detail sheet. | [12](../../reports/2026-11-01-phone-convenience-audit/evidence/12-row-edit-sheet.png) | 3AN3 with NF-3AD2 |
| P5 | medium | **A hidden second navigation.** The page name in the app bar has a ⌄ that opens a 13-place grid with names found nowhere else ("Safety", "Your data", "Profile and lock") and one bank icon for both Transactions and Accounts. Part C has no such menu: the tab bar and More are the navigation. | [13](../../reports/2026-11-01-phone-convenience-audit/evidence/13-title-menu.png) | 3AN2 |
| P6 | medium | **Needs you says "1 bill" for a certificate's interest match.** `_NEEDS_SHORT` in `routes/dashboard.py` files matches under payments; the bill truly due in two days is not in the strip. | [14](../../reports/2026-11-01-phone-convenience-audit/evidence/14-needs-you-open.png) | 3AN1, 3AN4 |
| P7 | high | **SMS capture is buried under Settings** on More, asks for an account it does not need, and its page has Accounts' tabs, no ‹, help as a paragraph and the Primary inside a card. For CIB and NBE users this is the fastest way to record money. | [04](../../reports/2026-11-01-phone-convenience-audit/evidence/04-more-full.png), [16](../../reports/2026-11-01-phone-convenience-audit/evidence/16-from-sms.png) | 3AN5 |
| P8 | medium | **Budget is a column of identical rows.** A-Z, 90 px each, a meter under every row, so 9 categories take 1.7 screens and the one at risk is wherever its letter puts it. On day one every row reads "0 of X / X left". | [02](../../reports/2026-11-01-phone-convenience-audit/evidence/02-budget-full.png) | 3AN7 |
| P9 | medium | **A buy reads as money out.** Transactions shows "Money market fund · Buy −3,000" in Ink with a minus, while Money out says 0 and the day's net (+46,833) leaves it out: what you see does not add up. It is a move inside your money (C08.2: investments on azure; moves carry no sign). | [03](../../reports/2026-11-01-phone-convenience-audit/evidence/03-transactions.png) | 3AN8 |
| P10 | medium | **Search in the app bar is for pages**, not money, says "Press Ctrl K", and needs a Search button (IV-3T3, reproduced). | [15](../../reports/2026-11-01-phone-convenience-audit/evidence/15-search.png) | 3AN6 |
| P11 | medium | **Day one is a wall of zeros.** Transactions "Money out 0", Budget all "0 of", Spending "0 in 2026-11", a Budget category says "Nothing matches", Investments keeps a 150 px card that says "Not enough history yet". Each should lead to something useful (last month, the plan, the holdings). | [08](../../reports/2026-11-01-phone-convenience-audit/evidence/08-spending.png), [07](../../reports/2026-11-01-phone-convenience-audit/evidence/07-investments.png), [17](../../reports/2026-11-01-phone-convenience-audit/evidence/17-budget-category.png) | 3AN9 |
| P12 | medium | **Arabic daily screens mix systems.** Figures in Arabic digits, dates in fields in Latin; the sign sits before one figure and after the next ("+٤٦٬٨٣٣", "٤٥٬٠٠٠+"); tile chips ("لحد دلوقتي", "اتصرف ٠٪") and the filter chips wrap to two lines. | [19](../../reports/2026-11-01-phone-convenience-audit/evidence/19-ar-overview.png), [20](../../reports/2026-11-01-phone-convenience-audit/evidence/20-ar-transactions.png) | 3AN10 |
| P13 | low | **At 320 a date breaks** across lines ("2026-12-" / "01.") in the hero sentence, and the "0% used" chip wraps (C12). | [18](../../reports/2026-11-01-phone-convenience-audit/evidence/18-overview-320.png) | 3AN1 |
| P14 | low | **Names differ for one place.** More says *Spending*; the page's title says "Expense analysis · Birdview" on two lines and opens on last month while every other tab opens on this one. | [08](../../reports/2026-11-01-phone-convenience-audit/evidence/08-spending.png) | 3AN9, 3AN12 |
| P15 | low | **More lists actions as settings:** *Needs you* and *From SMS* sit under Settings; a 50 px gap opens the page. | [04](../../reports/2026-11-01-phone-convenience-audit/evidence/04-more-full.png) | 3AN5 |

Still open and reproduced, filed elsewhere, not repeated: "Each month ahead" cut to "ach" and the forecast label over
its line (IV-3T1, IV-3T5); no ‹ on /sms, /search, /settings (IV-3T2); Settings' five tabs (IV-3T4); small targets on
Reserves 11, Prices 12, Financial health 9, Spending 15, Settings 14 (IV-3T3); Spending at 6 screens (3AN12); the
account page's "Money actions" and "All time" pill (3AN12). One question goes to the **number-audit** skill, not
here: Cash planning's "Each month ahead" shows 2026-11 as "In 0 · out 34,599" on the day the 45,000 salary arrived.

## The plan

### Five rules for every phone screen
These sit inside Part C; where one needs Part C to change, step 3AN0 asks the owner first.

1. **A job in three taps.** Every job above has a tap budget; a screen that adds a tap to a job is wrong.
2. **The answer, the next action, the latest money, all in the first screen.** About 680 px between the app bar and the
   tab bar. Analysis is a row that opens a sheet (D1, decided 2026-10-29).
3. **The thumb does the work.** What you press often sits low: Add in the tab bar, Save pinned above the keyboard, a
   sheet's actions at its foot. The top holds what you read.
4. **One surface at a time.** A sheet is the surface: no card inside it. A page is flat rows on the background; one card
   only for a lead figure or Needs you (C01.1, A16).
5. **Never a dead end or a wall of zeros.** An empty month offers last month or the plan; an empty chart is not drawn.

### Screen by screen
Each sketch is the first screen at 360 × 800. Figures are the sample's.

**Overview: "can I spend, and what moved?"** (P1, P2, P6; with 3AN12)
```
 [mark] Overview                       🔍  👁
 Safe to spend
 37,420 EGP
 About 1,247 a day until payday on 2026-12-01.
 ‹ 2026-11 ›                        (quiet text control, 40 tall, no pill)
 ┌ 2 need you · Landlord 12,000 in 2 days   Open ┐
 Net worth   215,322     │ Left in plan  25,599
 +52,896 this month      │ On pace · 0% used
 Latest                                   See all
 Today      ↓ CIB · Fees & Charges            −15
            ↑ ACME Egypt · Salary         +45,000
 Yesterday  ↗ Investments moved             +2,590
 ─────────────────────────────────────────────────
 [Overview] [Budget] ( + ) [Transactions] [More]
```
Two tiles, not four: the Lead already answers the page (C06.1 allows two). Savings and Investing rate move to Financial
health, where they are compared with their limits. Needs you names the next bill due within three days. Latest starts
near 520 px, so at least three rows are in view.

**Add: amount first** (P3, P7; builds NF-3AD1)
```
 ─────  Add                                     ✕
 [Out] [In] [Transfer]               [📋 Paste SMS]
 − 0  EGP                     (56 tall, number pad up)
 From  (Cash wallet ▾)        (last used, a chip)
 [Groceries] [Eating out] [Transport] [Bills] [Other…]
 Who  (optional, type and pick)
 Today ▾
 [        Save money out        ]   ← pinned above the keyboard
```
No account list first; no card inside the sheet; no "0.00"; no system sentence (what the entry does to the balance is
the chip's job). Paste SMS on top reads the message, finds the account from the card ending and opens the same sheet
filled in, so J2 is two taps. Saving shows "Saved · Undo" for five seconds above the tab bar and keeps you where you were.

**A transaction: look first, edit second** (P4; builds NF-3AD2)
A row opens a short sheet: the arrow chip, name, the amount in whole EGP, date and account, Category with Plan left,
Note; Change category and Split at the foot, Edit for the rest. For a row in *To sort*, the sheet leads with the usual
category chips and, after one tap, opens the next unsorted row (J5 in three taps).

**Transactions** (P9, P10; with 3AN12 and D2)
```
 Search transactions                       (live as you type)
 [All] [In] [Out] [Transfers] [To sort 3]  (one line, Arabic too)
 ‹ 2026-11 ›                         Select  ⋯
 In +46,833 · Out 0                        (one line, D2)
 Today                                +43,833
 ↗ Money market fund · Buy · THNDR   3,000   (azure, no sign)
 ↑ NBE · Interest · CIB Payroll     +1,833
```

**Budget: what needs a look, then the rest** (P8; with 3AN7)
```
 (ring 0%)  Left in plan 25,599  · You are 321 under your plan's pace.
 ‹ 2026-11 ›
 Eating Out        620 of 671  ▓▓▓▓▓▓▓▓▓░   51 left      ← over or ahead of pace first
 Food & Groceries  0 of 4,666  ░░░░░░░░░░ 4,666 left    ← then by what you usually spend
 …
 6 more on track ›
```
Rows 64 tall with the meter inside the row, not under it. On day one the hero line says "New month: 25,599 over 30 days"
and the list keeps the usual order. A row opens its sheet (3AN7): spent of limit, pace, the last three payments, Cover
it, See all, which keeps Budget chosen and the month, never a custom range.

**More: places, not actions** (P15)
Due soon, Your money, the Weekly review, then Settings with settings only. *From SMS* lives in Add; *Needs you* on
Overview. No gap above the first heading.

**App bar** (P5, P10)
The mark and the page's name, no ⌄ menu (More is the index; ‹ goes back). Search opens full screen, searches money first
(payments, counterparties, categories, amounts), live, then pages and actions, with no keyboard hints.

### The look, tuned for a phone (inside Part C)
- **Quiet chrome.** The month stepper is text with two 44 px arrows, no white pill; a disabled › is not drawn. Section
  headings 17 px, one hairline between rows, no shadow on rows.
- **Fewer, bigger figures.** Whole EGP on rows and fields as on figures ("45,000", not "45,000.00"); a percentage tile
  only where it is compared with something.
- **Rows that carry their meter.** Budget, reserves and limits draw a 4 px meter inside the 64 px row.
- **Sheets that own the screen's foot.** Grabber, a verb title, fields, then the Primary full width; with the keyboard up
  the Primary rides above it.
- **Arabic is its own layout, not a mirror** (P12): one digit system per screen, dates included; the sign always on the
  same side of the figure; chips shortened rather than wrapped ("اتصرف ٠٪" → "٠٪").

## Fix
Phone templates under `lightning/ui/templates/phone/` and `phone.css` (regenerate `phone.rtl.css`); `routes/dashboard.py`
(`_NEEDS_SHORT`, the tiles), `routes/register.py`, `routes/search.py`, the SMS route; figures keep coming from the
services, never templates. After each step: `tests/test_phone_*.py`, Mohab, `tools/phone_check.py` at 360 and 320, and the
audit's `evidence/flows.py` to recount the taps. Part C changes land in both repos in one session (AGENTS §1).

**Done when** the audit's table reads: Overview's first transaction row above 600 px; J1 3 taps with Save visible while
typing; J2 2 taps; J3 2 taps from Overview; J4 in the first screen; J5 search live from the app bar; no English word on
the Arabic daily screens; no page without ‹; then the owner checks the phone end to end (one check, at the end).

IV-3AL was folded into this item (owner, 2026-11-02): what it had left is 3AN12. `post: no` while Claude's claim holds the phone templates.

## 3AN0 Approve the Part C changes · owner
**Decided (owner, 2026-11-02):** (1)-(5) approved; (6) declined, the month stepper keeps its pill. Approved: (1) Overview
shows two tiles, Net worth and Left in plan; the rates live on Financial health (C11.1); (2) Add opens on the amount with
the last-used account chosen and usual categories as chips (C05.2, C09); (3) a row opens a detail sheet, Edit opens the
form (C09.7); (4) app-bar Search looks for money first (C03.2); (5) Needs you names the next bill due within three days
(C04.4). D1 and D2 (2026-10-29) ride with them. Next: write the five lines into Part C in both repos (AGENTS §1), then
delete this step.

## 3AN2 One navigation · S
Remove the ⌄ page menu from the phone's app bar (`phone/base.html`); the title is plain text. Check that every page it
reached is on More or behind ‹. Test: no `.phone-page-menu` in phone pages.

## 3AN3 The Add sheet and the transaction sheet · L
Built with NF-3AD1 and NF-3AD2, which own the flow; this step owns the look: no card inside the sheet, Save pinned above
the keyboard, category chips (usual first, from the services), whole EGP, Saved · Undo toast, To sort chains to the next
row. Done when J1 is 3 taps and J5's sort is 3 in `flows.py`.

## 3AN4 Overview's first screen · M
Two tiles, Needs you naming the next bill, Latest in view (first row above 600 px at 360 × 800).
Needs 3AN0 (1), (5); the stepper keeps its pill (owner, 2026-11-02). Mohab's Overview steps updated.

## 3AN5 SMS in Add · M
Paste SMS at the top of the Add sheet, with no account asked (From SMS already maps a card ending to an account once;
ask only for an ending it has not seen);
/sms gets ‹, one line of help and its Primary on the page; More drops From SMS and Needs you from Settings. Done when J2 is
2 taps.

## 3AN6 Search for money · M
App-bar search: live results, payments and counterparties first, then pages and actions; no "Ctrl K", no Search button.
Extends IV-3T3's search half; close both together.

## 3AN7 Budget in order of need · M
Over plan and ahead of pace first, then by usual spending; 64 px rows with the meter inside; "N more on track ›"; the
day-one line. With the category sheet (from IV-3AL2, folded here). Done when J4's row is in the first screen on the sample.

## 3AN8 Moves read as moves · S
A buy, sell or move between your own accounts shows with no sign on azure or Track (C08.2), so rows, Money in/out and the
day's net agree on screen. Test with the sample's money-market buy.

## 3AN9 No wall of zeros · S
On an empty month: Transactions, a Budget category and Spending offer "Last month" with its figure; Investments hides the
chart card until it has two months; Spending's title is "Spending" and it opens on this month like every tab.

## 3AN10 Arabic daily screens · M
Run the arabic-check skill on Overview, Add, Transactions, Budget and More: one digit system per screen, the sign on one
side, chips that fit one line at 360. Done when the Arabic shots show no English and no wrapped chip.

## 3AN11 Measure and hand to the owner · S
Re-run `evidence/flows.py` and the capture, fill the table with the new numbers in a dated follow-up of the report, run
Mohab and `tools/phone_check.py` at 360 and 320, then ask the owner for one end-to-end phone check.

## 3AN12 Left from IV-3AL · L
Folded from IV-3AL (Audit 10, [report](../../reports/2026-10-29-phone-tab-audit/report.md)); D1 sheets, D2 one-line money
strip, D3 flat (built). Overview: Your position as flat rows that open their pages; This period's figures as rows that
open a sheet (D1), never a fold inside a fold. Budget: a category row opens a sheet with its limit field, Cover it and See
transactions (with 3AN7); bulk undo, the raise offer and first limits take the strip's place one at a time. Transactions:
Money in and out as one line (D2); Views and value updates move into ⋯; a day's net only on a day with two or more rows.
Cash planning: forecast, months ahead and What is promised as rows that open sheets (D1). Recurring: the list first, the
fixed-costs ratio a link to Financial health, no ".00" on rows. Reserves: the app bar names Financial health; no card in a
card. Accounts: Accounts tab first (the section registry is shared with the PC: ask first). Investments keeps the owner's
PDF order. Spending: the lead (spent this month against the same days usually), four biggest categories then Other, then
one row "More analysis"; the heat map, both money-flow diagrams, small multiples and month grid leave the first page, and
the page renders under 150 ms. Tests: `tests/test_phone_frame.py`, `test_phone_budget.py`, `test_phone_transactions.py`.
