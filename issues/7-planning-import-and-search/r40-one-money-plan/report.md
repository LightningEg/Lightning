# Next milestone: one money plan. Usability, readability and the links between features

Date: 2026-11-27 · Author/reviewer: Claude, at the owner's request, with an audit by another AI that the owner pasted
Repository: app · Reviewed commit: e1426e498134b91ca0b4a298350b0d0cc51fa455
Code: r40 · App version: 2.3.3

## Assessment

Lightning has the features. It already covers more ground than Say or Qershnat: budget, cash planning, reserves,
goals, loans, gam'eya, zakat, investments, gold and two languages. What stops it from feeling like one product is that
**each screen tells its own version of the month**. On one day (27 Nov, payday 1 Dec, Mohab's sample) the app gives
seven different "what is left" figures, and its headline sentence says *"You can spend 51,420 today and stay on
plan"*. That is true by the formula, but only because about 19,400 of each 45,000 salary has no job in the plan and
piles up into Safe to spend.

Every figure is correct by its own definition. Nothing here is wrong money in the ledger. The problem is readability
and the links between figures: a person who opens Home, then Budget, then Plan cannot tell how the numbers relate.

**The next big milestone is one money plan:** one monthly flow (money in → bills → everyday → savings and goals →
no job yet) that every screen reads from, a nudge that gives unassigned money a job, and payday as the moment that
opens the month and a short review that closes it. It is mostly linking and wording on top of what is built, not new
engines. The competitor check (below) says the same: bank-SMS capture is now common in Egypt, so the coherent,
private, whole-picture plan is where Lightning can win.

## Owner direction (asked in this session, 2026-11-27)

| Question | Answer |
| --- | --- |
| Which milestone next? | Report every finding, the next big milestone and a competition check (this report) |
| Safe to spend holds money the plan never assigned. What should it do? | **Keep the figure, add a nudge** under it that offers to give the unassigned part a job |
| What now? | **Start the clean-up PR** (the fixes marked "Fixed" below) |

## Scope and method

- Mohab's sample year, dated 2026-11-27 (four days before payday), English and Arabic.
- Phone at 360 and 320 px (`tools/phone_check.py`, its pages and screenshots); PC at 1366 × 800 (Overview, Cash
  planning, Budget), screenshots in [evidence/](evidence/).
- Read alongside: r35 (users' questions), r36 (one figure, one owner), r37 (cash planning workflow), r38 and r39 (PC
  usability), Project Overview §6 and §7, Competition, and the code behind each finding.
- The other AI's audit (desktop 1366 × 800; phone 360 and 320 px; reviewed at the same commit): its findings are
  F1 to F6 below, each checked again here.

## Findings

### A. One story: figures that disagree when shown together

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | high | **Phone Plan listed bills after payday under "Before payday".** With nothing due before 1 Dec, the salary, the landlord (3 Dec) and the car loan (5 Dec) sat under *Before payday* with Pay buttons, right after "Nothing is due before payday". | [before](evidence/phone-plan-before.jpg), [after](evidence/phone-plan-after.jpg) | Fixed: they have the *After payday* section, which keeps the page's anchor, the Calendar link and the sentence naming the next payment. `tests/test_phone_cash_planning.py` |
| F2 | high | **Home's "About 331 a day" reads as Safe to spend split by day.** It sits under *Safe to spend 51,420* but is Budget's everyday figure (1,324 over four days). | [phone Home](evidence/phone-home-before.jpg) | Fixed in part: the line now opens Budget (`tests/test_one_daily_allowance.py`). Renaming it *Everyday budget: about 331 a day* changes guideline C11.1's wording, which must land in the website repo too; that repo was not reachable from this session. Owner pick: inbox |
| F7 | high | **Seven "what is left" figures on one day.** Home: Safe to spend 51,420, about 331 a day. Phone Plan: "You keep 61,744 until 1 Dec" (Free cash). Phone Plan: Going out over 30 days 15,980 (bills only; everyday spending is not in it). Phone Budget: Left for everyday 1,324, Planned 9,619. PC Overview: Left in plan 1,324 of 25,599 planned. PC Cash planning: Lowest point ahead 51,420, "10,324 below today". | [phone](evidence/phone-plan-before.jpg), [PC](evidence/pc-cash-planning-before.jpg) | Milestone, step M1 |
| F8 | high | **The headline sentence invites spending money the plan never assigned.** PC Cash planning: "You can spend 51,420 today and stay on plan" four days before a 45,000 salary. The budget plans 25,599 of the salary (bills 15,980, everyday 9,619); the rest has no job, so whatever is not moved piles into Free cash and then Safe to spend. Nothing asks what it is for: this is Overview §6 gap 6 ("give every pound a job"), still open. | [PC](evidence/pc-cash-planning-before.jpg) | Owner: keep the figure, add a nudge. Milestone, step M2 |
| F9 | medium | **"Planned" means two numbers.** Phone Budget: Planned 9,619 (everyday). PC Overview: 25,599 planned (bills and everyday). Both lead to Left 1,324, so the parts are right, but the word names different totals. | [phone](evidence/phone-budget-before.jpg), [PC](evidence/pc-overview-before.jpg) | Milestone, step M1 |
| F10 | medium | **The 30-day view leaves out everyday spending.** Phone Plan: Coming in +45,000, Going out 15,980. A reader sees about 29,000 spare; the everyday budget (about 9,600 a month) is not in *Going out*. | [phone Plan](evidence/phone-plan-before.jpg) | Milestone, step M1 |
| F11 | low | **Lowest point ahead repeats Safe to spend** (51,420 twice on Plan) and compares with Free cash ("10,324 below today"), a third figure. Already r37 L6. | [PC](evidence/pc-cash-planning-before.jpg) | Inbox (r37 L6); milestone step M1 |
| F12 | low | **PC Overview "Next 7 days: 12,000 to pay, of 0 left this month".** The week ran into December; "left this month" counted November only. | [PC Overview](evidence/pc-overview-before.jpg) | Fixed: a week that runs past the month end says "12,000 to pay this week". `tests/test_upcoming_calendar.py` |

### B. Links between features

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F13 | high | **Payday drives the whole month, but its screen is hard to find.** The payday step (bills protected, your plan, emergency and goals, left unassigned) is built, but on the PC it is in Cash planning's ⋯ menu ("Fund your payday plan"); on the phone it is a row on Budget. Nothing opens it when the salary lands. | code: `planning/plan.html` top actions | Milestone, step M3 |
| F14 | medium | **One overspend, two offers on two screens.** Budget: "Move it: 22 from Shopping"; To do: "Transportation 22 over plan → Adjust". | [Budget](evidence/phone-budget-before.jpg), [To do](evidence/phone-todo.jpg) | Milestone, step M4 |
| F15 | medium | **Budget and Cash planning meet only in one line each way.** Budget shows "Fixed bills and savings 15,980 · From Plan"; Cash planning's breakdown links to Budget (IV-7AX). Neither says what the salary is split into, so a person cannot see the month as one plan. | [Budget](evidence/phone-budget-before.jpg) | Milestone, step M1 |
| F16 | low | **Overview's "Plan to invest" sits on Free cash, not on what has no job.** It is the right link (unassigned money → investments) placed on a figure that includes money already promised. | [PC Overview](evidence/pc-overview-before.jpg) | Milestone, step M2 |

### C. Readability and calm

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F4 | medium | **PC Transactions: "Choose an account" leaves the register** while the register has an inline New row. | other audit | Not done: owner decision r38 F1 (no Add button; adding lives in the account; Transactions keeps "Choose an account") |
| F5 | medium | **To do mixes work with suggestions.** "8 things need you": an SMS to file and two interest payments to match beside "Make it a bill" offers, a 5 EGP and a 22 EGP overspend, and a top-up. Every row has the same weight, and small amounts make the count look urgent. | [To do](evidence/phone-todo.jpg) | Owner pick: grouping or a threshold changes what the count shows (A09.2 says it counts every item). Inbox |
| F6 | medium | **PC calendar shows the payee's first letter** (L, V, W), so finding a bill means opening the day. | [PC](evidence/pc-cash-planning-before.jpg) | Inbox |
| F17 | medium | **PC "Due before payday 0 EGP · 0 payments before payday · Nothing else is due before then"** while the rent falls two days after payday; the phone already says "All covered" and names the next payment. | [PC](evidence/pc-cash-planning-before.jpg) | Fixed: the card says **All covered** · Nothing is due before payday, and names the next payment with a link to Upcoming. `tests/test_bills_before_payday.py` |
| F18 | low | **Safe to spend's card says it three times:** "83% of your free cash", "On top of your plan", "Expected by payday 51,420". | [PC](evidence/pc-cash-planning-before.jpg) | Milestone, step M1 |

### D. Small screens

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F3 | high | **At 320 px Budget's Dismiss ran 6 px past the screen** (and was cut at 360 too); the Settings theme picker ran 33 px past in English, 26 px in Arabic. The earlier picker fix lost to the 210 px cap's higher-weight rule. | `python tools/phone_check.py` | Fixed: the change row's actions wrap under the text in a row; the picker shrinks to its row. `phone_check.py` passes at 360 and 320 in English and Arabic |

## The milestone: one money plan

**Goal.** Every headline figure on Home, Budget, Plan and Overview is one line of the same monthly flow, has one
name, and opens its place in that flow. Money the plan has not given a job is named and gets a one-tap nudge. Payday
opens the month and a short review closes it. Everything is a suggestion the person confirms (owner, 2026-11-09).

**Why this, why now.** The phone launches on Google Play on 1 December. New users judge an app in its first week,
and what they see on Home is the ladder, Safe to spend and the line a day. If those disagree with Budget and Plan,
the app looks wrong even though the ledger is right (compass rule 5: a wrong number is worse than a missing one).
Bank-SMS capture is now common among Egyptian apps (see Competition, below), so a plan that adds up on every screen,
privately and offline, is Lightning's edge.

| Step | What | Builds on | Done when |
| --- | --- | --- | --- |
| M1 | **One flow, one name per figure.** A *Your month* breakdown (money in → bills → everyday → savings and goals → no job yet) that Budget, Plan and Overview each show the same way; drop the duplicates (F7, F9, F10, F11, F18). | the Safe to spend working, NF-12AB explain-in-place, the Glossary | each figure in F7 appears once with one name; Mohab's year and `tests/test_figures_agree.py` agree |
| M2 | **The nudge** (owner: keep the figure). Under Safe to spend, when part of it is beyond the plan's needs to payday, one line: "*N* has no job yet" with Emergency fund, a goal, Invest, or Keep (F8, F16). | Reserves, goals, the investing planner, Refill | a test reads the line on Home and Plan and each choice opens its page prefilled; nothing moves until confirmed |
| M3 | **Payday opens the month.** When the salary is recorded or read from an SMS, the phone notifies and Home offers the payday step; Plan and Budget link to it by name, not from a ⋯ menu (F13). | `/payday`, the Android reminders, IV-7AX | marking the salary received offers the step on both surfaces |
| M4 | **One offer per problem.** Budget's Move it and To do's Adjust become one suggestion, shown where the problem is and counted once (F14); To do's grouping as the owner picks (F5). | IV-12AA, the Needs you groups | one overspend gives one row across screens |
| M5 | **The month closes with a review.** The monthly review (#638, NF-12AL, already ready on the board) says what changed and whether the plan held, from the same flow. | NF-12AL | its figures are M1's |

**Not in this milestone:** a visual restyle, more asset kinds, shares in Europe and the Gulf, household sharing. The
board already holds 25 open items, above AGENTS.md's 20; this milestone should replace parked items, not sit beside them.

## Competition, 2026-11-27

Details and sources are in [Competition › Field check, 2026-11-27](../../../ai/COMPETITION.md#field-check-2026-11-27).
In short: Say now reads bank texts and app notifications, shows all banks and apps in one list, has widgets and a
**shared household budget**; Qershnat is on 5.x with a redesign and keeps widening (crypto, medicines); several new
Egyptian trackers (Pockito, Masareef on iPhone) read bank SMS and add an AI helper. Copilot's assistant and Monarch's
make suggestions and ask before changing anything, as Lightning's smart features do. **Bank-SMS capture is table
stakes now.** What none of the Egyptian apps show is one plan that adds up across budget, bills, savings and
wealth, privately on your own devices. That is this milestone. Household sharing is the gap to watch next.

## What works and should be kept

- The phone's quick-action strip (Expense, Income, Transfer, Pay a bill): four everyday jobs, one tap each.
- The ladder on Home (Cash and banks → Free cash → Safe to spend), each step opening its working.
- PC Cash planning's *How safe to spend is worked out* with rows that open their pages, and Overview's *How it adds up*.
- Budget's *Move it* and *Fill*: suggestions with nothing changed until you choose.
- Paying a bill: one popup, Undo, every figure moved by the right amount (r37).

## Validation and limits

- Source and browser evidence on the sample household only; no real phone, no real data, default theme only.
- `tools/phone_check.py` (English and Arabic, 360 and 320 px) on Home, Budget, Plan and Settings after the fixes:
  nothing scrolls sideways or clips.
- The full test suite was run before the pull request; see its description.
- Competitor facts are from store listings, vendor pages and third-party reviews read on 2026-11-27; versions and prices
  disagree between sources, as Competition notes.

## Dated follow-ups

Append dated dispositions here; keep the findings above as written.

- **2026-11-27:** at the owner's request, [r41](../r41-the-next-big-thing/report.md) places this milestone as phase 1 of the next big thing (the payday plan that fills itself).
