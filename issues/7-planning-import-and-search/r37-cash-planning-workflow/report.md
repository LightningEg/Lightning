# Audit 20: the cash planning and forecasting workflow, used as a user

Date: 2026-11-14 · Author/reviewer: Claude
Repository: app · Reviewed commit: 1ea4749237ffdaf1eeb01617f9f69e3688d90364
Code: r37 · App version: 2.2.1

## Assessment

Reading Cash planning is good: Safe to spend leads, the way it is worked out is shown, paying a bill is one popup with
an Undo, and every figure moved by exactly the right amount when a bill was paid. The trouble starts when you **act on
the plan**. Doing the saving the plan asks for is counted twice (W1), the instalment offer and the scenarios contradict
themselves (W2, W3), and three sentences state a figure that is not true (W4, W5, W8). Behind that, the pieces are not
joined: the breakdown's rows lead nowhere, the payday step cannot be found from Cash planning, and a purchase you
checked cannot be planned.

r32 (2026-11-09) audited how these pages look and left the actions unchecked. This audit is those actions.

Order: W1 (wrong figure after every saving move); then W2-W5 (contradictions on screen); then the joins (L1-L3); then
the pain points.

## Scope and method

Every page of Cash planning and what it leans on: `/plan`, *Can I afford this?*, `/plan/upcoming`, `/plan/recurring`,
`/plan/loans`, `/plan/scenarios`, `/plan/inputs`, `/plan/catch-up`, an item's sheet, pay, edit and early-payment pages,
the new item, loan and instalment forms, `/plan/reserves`, `/payday`, and the same figures on Home and Budget.

The demo household (`python -m lightning --demo`), date 2026-11-14, PC at 1366 x 768 in Chromium; the phone app at 360
px through `tools/phone_check.py`. I acted as a user: checked purchases, paid a bill, tracked a suggestion, added
bills, a second income, a one-off, three loans, a savings goal, walked late payments, refilled the emergency fund,
turned cash funding on and confirmed it, recorded the salary early, and ran each scenario. After each step the figures
on Plan, Home, Upcoming and Budget were read again. Forms also got blank, zero, negative, letters and bad dates.
Scripts: [flows/](evidence/flows/) (their first line says how to run them). The demo was restarted between journeys.

## Findings

Severity: high = a wrong figure; medium = a contradiction, a dead end or a false sentence; low = polish.

### Incorrect

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| W1 | high | **This month's saving is counted twice.** Safe to spend is 51,420 after an *Emergency fund top-up* of 5,404. Press *Refill 5,404* on Reserves: Safe to spend falls to 46,016 and the plan asks for another 5,179 this month. On `/payday` the page says "Safe to spend stays at 46,016 EGP"; after *Confirm cash assignments* it is 38,172, and the page offers a fresh proposal at once ("Confirm to give 7,332 a job"), which can be confirmed again and again in the same month. Cause: the top-up is the gap ÷ 24 with no memory of what moved this month (`lightning/budgeting/domain.py:244`, used at `lightning/planning/forecast.py:302`); goals behave the same (2,667 a month became 2,370 more). Expected: a top-up or goal move made this month counts against this month's ask, so Safe to spend does not move. [After confirm](evidence/pc-payday-after-confirm.png). | proposed item |
| W2 | medium | **Refill in instalments offers all of Safe to spend, then goes below zero.** Under "keep Safe to spend at or above zero where they can" the rows are: 1 Dec 51,420 (Safe to spend after 0), 1 Jan −51,420, 1 Feb −78,273. The rows are dated in future months but worked out on today's cash, so no later salary is counted (`forecast.py` `refill_schedule`). [Screenshot](evidence/pc-reserves-instalments.png). | proposed item (with W1) |
| W3 | medium | **Compare scenarios contradicts itself.** Buy 60,000 on 20 Nov: lead figure −8,580, and beside it "First shortfall · Scenario: No shortfall"; the headline says only "lowers your lowest point ahead by 60,000". *Can I afford this?* answers the same purchase "Only by cutting your plan". Salary 20 days late (1 Dec to 21 Dec): "leaves your lowest point ahead where it is", because the lead is month-end only. Two models (scheduled cash by day, free cash by month end) share one page. [Screenshot](evidence/pc-scenario-below-zero.png). | proposed item |
| W4 | medium | **Upcoming: "2,000 more than October" when both months are 17,980.** December says "2,000 more than November" too. This month's total counts the gam'eya instalment; last month's does not (`lightning/planning/calendar.py:126` `_out_total`). [Screenshot](evidence/pc-upcoming.png). | proposed fix |
| W5 | medium | **Recurring: "Your bills take 13,480 a month, 36% of your income."** 13,480 is 30% of 45,000; 36% belongs to 15,980 (bills and the loan), the card beside it. | proposed fix |
| W6 | medium | **Any income becomes "payday".** Adding an 8,000 side income on the 25th turned "until payday 1 Dec" into "until 25 Nov" on Plan and Home, and *Lowest point ahead* stopped matching Safe to spend. The Glossary says payday is the salary day. On Upcoming, on 14 Nov, the hero still shows "Payday 1 Nov · Coming in 45,000", which already arrived. | owner decision |
| W7 | low | **The date in *Can I afford this?* does nothing without an account.** 30,000 on 10 Dec (after payday) and on 2025-01-01 both answer "Yes. You keep 21,420 safe to spend until 1 Dec." With an account chosen the card says "Fits your plan: Yes" above "not enough from today". | inbox |
| W8 | low | **Payday proposal.** "Bills protected 0 EGP" above a list of two bills due before payday (they sit inside "To your plan"); parts are one pound off the plan (5,403 against 5,404; 2,666 against 2,667). | inbox |
| W9 | low | **Loans: two totals.** "52,500 left to pay on 1 loan" above "66,500 owed against net worth"; the 14,000 gam'eya is named only on Plan. | inbox |
| W10 | low | **Adding a bill today rewrites past months.** A bill added with four past due dates changed September's and October's month-end free cash on the chart (60,456 to 60,256; 79,636 to 79,336). | inbox |

### Not linked

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| L1 | medium | **The breakdown's rows lead nowhere.** *Budget until payday*, *Emergency fund top-up*, *Rest of savings target* and *Saving for goals* are plain text: no way to Budget, Reserves or the savings target that sets them. On the PC, Reserves is not reachable from Cash planning at all; the phone's Plan has a Reserves card. | proposed item |
| L2 | medium | **The payday step is hidden.** `/payday` is linked on the PC only from the weekly review's folded actions. It lights Budget in the sidebar while its only button says Cash planning. Nothing offers it when the salary is marked received, which is the moment it is for. | proposed item (with L1) |
| L3 | medium | **A checked purchase cannot be planned.** *Can I afford this?* offers "Record this purchase" only after an account is chosen, and only as a transaction today. A scenario saves nothing. To put a purchase in January into the forecast you must find *Add recurring item* and set Repeats to Once. | proposed item (with W3) |
| L4 | low | **Savings goals are worded as bills, under Safety.** A goal shows as "Upcoming payment · due 1 Jul 2027", "Link or review a payment", "Match by: Ask"; saving it answers "Most you can plan this month is now 36,000". Cash planning has no word about goals except one row. | inbox |
| L5 | low | **Budget month against payday period.** *Budget until payday* is the rest of the calendar month's everyday budget whatever the payday date; the forecast table labels whole future months "Budget until payday" too. | inbox |
| L6 | low | **One figure twice.** *Lowest point ahead* is Safe to spend again in the usual month (51,420 twice on Plan). | inbox |
| L7 | low | **"3 more in the next 30 days · Recurring"** links to Recurring, which does not list loans; the row it hid was the car loan. Upcoming is the page that has them all. | inbox |

### Pain points

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| P1 | medium | **A bill without a category cannot be paid.** Category is optional when you add an item; paying it answers "Give Old bill a category first" (shown twice), with no category field and no link. In Catch up this stops the flow. | proposed fix |
| P2 | low | **Catch up is one payment at a time.** Four late months of one bill are four rounds; no "all paid" or "skip all". | inbox |
| P3 | low | **No duplicate warning.** The same income, name and date added twice is accepted; the forecast then counts 16,000. | inbox |
| P4 | low | **Two forms for one thing.** *Add loan* (payment, count, amount borrowed) and *Bought in instalments* (price, count, fee) make the same kind of plan; the second is a link that reads as the heading over every loan. | inbox |
| P5 | low | **The next 30 days.** Capped at seven rows with the gam'eya row always last, out of date order (r32 noted it), so it stays while the 2,500 loan payment is folded away. | inbox |
| P6 | low | **Form polish.** Radio circles show above the Type pills in the add popup ([screenshot](evidence/pc-add-item-popup.png)); amounts with ".00" (pay, instalment preview "3,100.00", pay early "10,000.00") and raw "−60000 EGP", "12000.00 → 15000" in scenarios (A16: whole EGP); "Matching: how a bank transaction is matched to this plan". | inbox |
| P7 | low | **Jargon cards.** "Scheduled cash checks ... Unassigned scheduled payments are included in combined cash using your profile currency" appears on Plan when an item has no account; Scenarios' "How this is worked out" reads the same way. | inbox |
| P8 | low | **A clipped table.** *In and out each month ahead › Show the numbers* is cut at the right edge at 1366 px; the Out column cannot be read. [Screenshot](evidence/pc-plan-after-adding-items.png). | inbox |

### Missing

| ID | Observation |
| --- | --- |
| M1 | The phone has no *Can I afford this?* (no phone template holds it). |
| M2 | No day-by-day low for free cash: the forecast is month-end, so a late salary or a big bill before payday cannot be seen (W3). |
| M3 | "Bill changes" moves one occurrence only; a rent rise that stays cannot be tried. |
| M4 | Phone Scenarios still shows "Lowest scheduled cash 85,730" beside "Lowest point ahead 51,420"; the PC shows only the second. |
| M5 | A loan is its payments (Glossary): a bank loan of 80,000 repaid as 36 x 3,000 lowers net worth by 108,000 the moment it is added, and what was bought is not an asset. Stated here for the owner's eye, not as a bug. |

### What works

- Paying a bill: one popup, the budget effect shown first, back on Plan with Undo; Free cash, Due, Home, Upcoming and
  Budget each moved by exactly 650, and Safe to spend stayed.
- *Track* a suggestion: prefilled, and the answer says what it does to fixed costs against the limit.
- Form checks speak plainly; 15/12/2026 and Arabic digits are accepted.
- Salary recorded early: the plan moves to "until 1 Jan" and holds two months back. A goal is taken out of the savings
  target, not on top of it.
- Pay early previews the new end date. The phone's Bills page splits before and after payday.

## Validation and limits

Browser evidence on the demo household; figures were read from the pages, with the cause read in code for W1, W2 and
W4. No code changed, so the suite was not run. Not checked: Arabic, themes, the Android app itself, the `.ics` file, a
gam'eya's own page, certificates, other currencies, the phone's forms beyond a look at each page.

## Dated follow-ups

