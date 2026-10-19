---
title: Tab-by-tab review: what a real user needs next
type: polish
area: product
status: building
created: 2026-10-14
by: Codex
---

# Tab-by-tab review: what a real user needs next

**Status:** implementation started, 2026-10-14 · Codex; remaining work is below. A full walk through every section and tab as a demanding salaried user, on PC (1366 × 768) and phone (360 wide). When an item is built, move what holds into [Architecture](../../docs/ARCHITECTURE.md) or the [Project Overview](../../docs/PROJECT_OVERVIEW.md), tick it here, and delete this file once it is empty.

**How it was done.** A fresh encrypted profile (`profile_app`, the same pages as the Windows app) with the sample household (`POST /demo`, Mohab, 2026-08 to 2026-10-14), zakat turned on and a 10-member gam'eya joined late, exactly as `tools/phone_check.py` sets it up. Every page in `lightning/ui/sections.py`, plus holding, certificate, gam'eya, register, transaction, import, reconcile and settings pages, was captured full-page on PC and phone and read figure by figure. Every number quoted below is from that run, so anyone can reproduce it.

**How to read it.** Each item has an id (say "build OV-4"), a kind and a priority:

- **Kind:** *Logic* (a figure or rule), *Visual* (layout, guideline), *Flow* (steps, clicks, navigation), *Tech* (code, speed, tests), *Feature* (new).
- **P1:** a wrong or misleading number, a broken screen, or an A16 failure. Fix before the next release.
- **P2:** friction a daily user feels every week.
- **P3:** polish or a new idea worth scheduling.

Items that need the owner first are marked **(owner)** and gathered in section 12. Existing proposals are linked, not repeated.

## Contents

| Section | Read it when |
|---|---|
| 1. The fifteen that matter most | You have one sitting |
| 2. Across every tab | You touch figures, periods, charts or layout anywhere |
| 3. First run and profiles | You work on setup, samples or the profile chooser |
| 4. Overview | Summary, Spending, Health, Currencies |
| 5. Budget | The Budget section and its settings |
| 6. Cash planning | Plan, Recurring, Loans, Reserves |
| 7. Investments | Holdings, a holding, certificates, Planner, Prices |
| 8. Accounts | Accounts, a register, Transactions, Held for others, Zakat, Gam'eya, import, SMS |
| 9. Settings and search | Your data, Categories, Counterparties, Rules, Data checks, Ctrl-K |
| 10. Phone only | Part C screens |
| 11. Technical | Speed, tests, CSS, time, safety |
| 12. Decisions for the owner | Before building anything marked (owner) |
| 13. New features an Egyptian salaried user will ask for | You plan the roadmap |
| 14. Suggested order and Mohab steps | You pick what to build |

## 1. The fifteen that matter most

Ranked by harm to trust, then by how often a user meets it.

| # | Id | What is wrong | Fix in one line |
|---|---|---|---|
| 1 | SP-1 | Spending compares 1–14 October with all of September: "Money out 18,659, −25% against 2026-09" in green | Compare the same days of the earlier month, or say "so far" and grey the chip |
| 2 | X-3 | XIRR annualizes a few weeks: gold pound +241.5%, COMI +106.8% "a year", portfolio +65.8% | Under 12 months show the plain return; XIRR only from one year held **(owner)** |
| 3 | CP-1 | Two "a day" figures disagree: Budget "about 336 a day", Cash planning "about 2,172 a day", same 18 days | Safe to spend's line becomes "on top of your plan"; one daily figure, on Budget |
| 4 | IN-2 | A certificate's interest is not in its return: NBE 3-year shows Gain 0, Return 0.0% after paying 3,667, and the 3,667 sits under "Dividends collected" | Total return = price change + income; rename to "Income collected (dividends and interest)" |
| 5 | AC-2 | PC registers show an outgoing transfer as "1,000" with no sign, while the balance falls by 1,000 | "To Vodafone Cash −1,000.00", as the phone already does (OWNER 2.1) |
| 6 | GA-1 | A gam'eya joined late says "Nothing owed either way" while three instalments (6,000) are unpaid and the 20,000 turn date has passed | Say what is owed both ways; offer "Record the missed instalments" in one step |
| 7 | IN-3 | Holdings after sale is 74,007 against a 177,903 portfolio; Settings › Sale factors still shows CDs at 95,000 after sale | Settings and the figure must agree: show the locked certificate as 0 "locked until 2027-08-01" in both |
| 8 | X-1 | The floating page-jump button sits on top of right-aligned figures ("57,1⌄" on Zakat, "480.0⌄" on Recurring, "469" on Spending) | Reserve a gutter for it, or move it to the sidebar foot |
| 9 | RS-1 | Emergency fund 0.4 months and "target is more than the cash you own" for someone with 55,560 free cash and 100,000 in a certificate | Count the target in months of spending, or show both, and name what else could cover it **(owner)** |
| 10 | HL-1 | Holding page: "Worst month +2.7%" in strong rose next to "Best month +2.7%" in green (A16: KPI by position) | Tone by sign; with one month, show one figure |
| 11 | OV-1 | Phone Overview puts six latest transactions above Needs you, which hides the overdue gam'eya instalment below the fold | Needs you first, then the four tiles, as the owner decided (2026-10-06) |
| 12 | FR-1 | "Add the sample household" fills the user's own, real profile | Samples open in their own throwaway profile; never inside a real one **(owner)** |
| 13 | SE-1 | Budget settings read "the same asRecurringon Categories" and "the same asOne-offon Categories" (missing spaces) | Fix the inline links' spacing; add a rendered-text test |
| 14 | X-2 | One figure, two looks: sidebar "CIB Payroll 71,624.86", page header "71,625", register "−469" while the phone says "−468.50" | A06.1 everywhere: totals whole, rows two decimals, same on PC and phone |
| 15 | CP-4 | Recurring items are listed Landlord (11-03), Electricity (10-24), Internet (10-20), ACME (11-01) | Sort by next date; overdue first |

## 2. Across every tab

**[x] X-1 · Visual · P1 — The page-jump button covers figures.** `#page-jump` (`app.js` line 254) floats at the right edge, exactly where right-aligned amounts end. Seen on Zakat, Recurring, Loans, Spending, Budget, Prices, Health, Categories. Give the main column a right padding equal to the button, or dock the button in the sidebar under the account list. On the phone it is fine; the issue is PC.

**[x] X-2 · Visual · P1 — The same amount is written three ways.** Sidebar and Accounts table keep cents (263,462.36), headers round (71,625), the PC register rounds rows (−469) while A06.1 says rows keep two decimals and the phone register does (−468.50). Make one helper decide by role (total, row, field) and use it on PC and phone; add a test that the same transaction renders the same text in both.

**[x] X-3 · Logic · P1 (owner) — Annualized returns on short histories.** `XIRR` is shown from day one (Overview of Investments, holdings table, holding page, certificate row). A ring bought this month or a share held five weeks produces three-digit "a year" figures that no user can act on, and feedback row 61 shows users already doubt it. Proposal: under 365 days show *Return* (simple, not annualized) with "held 5 weeks"; from 365 days show XIRR. Keep the calculation; change what is shown.

**[x] X-4 · Logic · P1 — Part of a period against a whole one.** Wherever a running period is compared (Spending's "Against 2026-09", "Against your usual month", "Now against your usual month" bars, Overview's Change in net worth early in the month), compare like with like: days 1–14 against days 1–14 of the earlier month(s), or extrapolate and say "on pace for". Mark a running period "so far" and do not colour its chip green or rose until it is complete, because a half month always looks thrifty.

**X-5 · Logic · P2 — Charts with two points.** The data has three month-ends, yet charts draw lines, "lowest" and "best" labels as if there were a history: Health's Savings rate line runs diagonally across an otherwise empty plot with one month named; Holding page "Typical move — after three months" is right, "Months up · down 1 · 0" and "Fall from its high 0" add nothing. Rule: below three points, show the number and the sentence "a line appears after three month-ends", never a line. Net worth on Health already does this; do it everywhere.

**X-6 · Logic · P2 — Labels that do not match the data.** "Usual: the average of the last 6 months" when the header says "the 2 months before it"; Reserves "Average monthly income … 2026-07 to 2026-09 · 2 months with income" under a "3 months" setting. The label must state the months actually used.

**X-7 · Flow · P2 — Period controls are not the same everywhere.** Overview, Spending, Budget and Investments have the four-choice picker; Health has "As of [date] Show"; Cash planning has none; Currencies shows the picker on an empty page; Settings › Export for AI has its own. Keep the picker only where a period changes the answer, give Health the same picker (Health reads month ends), and hide it on empty states.

**X-8 · Flow · P2 — Every figure should open its rows.** Feedback row 54–55 asked for it; today a card opens a tab, a chart, nothing, or a popup depending on the page. Rule: a money figure opens the transactions behind it (filtered register), a ratio opens its "Show the numbers", a forecast opens the plan line. Write it in Architecture › UI contract and test one card per tab.

**X-9 · Flow · P2 — Saving reloads the page.** Saving a reserve, a rule or a category posts and redirects. `app.js` restores the scroll (line 58), but focus and open folds are lost and the free-cash cards stayed stale in feedback row 67. Where a field already autosaves (budget rule, reserve amount), update the dependent figures in place from the response; elsewhere keep the redirect but return to the edited row (`#row-id`) with its fold open.

**X-10 · Feature · P2 — Pay-cycle months (owner).** Salaried Egyptians are often paid on the 25th or the 1st, and many think "the month" runs payday to payday. Budget, Spending and Cash planning are calendar months only. A setting "My month starts on day [1–28]" would make "Left in plan", "Money out" and Safe to spend match how the user lives. Large change: periods (`ui/periods.py`), budget months, health months.

**X-11 · Feature · P2 — Reminders.** Already "Next up" in the Roadmap. From this walk, the reminders a user needs, in order: a bill or loan due tomorrow; a gam'eya instalment; expected salary not seen two days after its date (left out by decision; ask again); certificate interest day; zakat day (when on); month-end prices; no backup for 14 days. Windows toast and Android notification, each opening the matching Needs you row.

**X-12 · Visual · P2 — Gear and tab bars waste a row.** Budget has one tab, so its gear sits alone on a full-height row above a half-width alert card, leaving the top right empty. When a section has one tab, put the gear in the page header's actions.

**X-13 · Visual · P3 — Two-line names wrap to three.** "Commercial International Bank (COMI)", "Gold pound (from grandma)" wrap three lines in Biggest holdings; Allocation legend wraps "Total · 70% of what you own". Use the short name (ticker or nickname) in charts and the full name in tables.

**X-14 · Flow · P3 — Undo.** Built locally 2026-10-15: edits, imports and grouped reviews use session undo/redo. Read Architecture › Action history and checked accounts. Behavioural acceptance remains outstanding.

## 3. First run and profiles

**FR-1 · Flow · P1 (owner) — Samples go into the real profile.** The welcome page offers five samples that fill *this* profile, with a small line suggesting a separate profile. A tester who clicks it then deletes nothing and starts typing real money next to Mohab's. Proposal: "Try with sample data" creates a temporary profile named "Sample · Mohab" with a known password-free unlock (or the same password), clearly banded "Sample data" on every page, and "Delete sample" in Profiles.

**FR-2 · Flow · P2 — Ask the two numbers that make every tab work.** After the first account, ask: "How much is your salary, and on which day does it arrive?" That one answer creates the recurring income, the average monthly income, the budget room, the emergency target and Safe to spend's next income. Today these tabs show "No baseline yet" or a 0.4-month emergency fund until months of data exist.

**FR-3 · Flow · P2 — Gam'eya is missing from "Where do you keep your money?"** The five starters are Bank, Cash, Certificates, Brokerage, Gold. Add "Gam'eya" (it is an account type) and "Foreign cash" (dollars at home), the two most Egyptian holdings.

**FR-4 · Visual · P3 — Sample buttons touch the next heading.** "Add the sample household" and "Load Mohab's 2026" sit directly on the following title. Use the standard section gap (A15).

**FR-5 · Flow · P3 — Recovery key confirm.** The key is shown once with "I saved it". Offer "Save as a file" and "Print" next to it (the user is at a PC), and on the phone "Copy". Never store it.

**FR-6 · Visual · P3 — Profile page path.** "Will create: /tmp/…/Mohab_2026-10-14_001_cbe85d8b.db" shows a long technical path on the setup page; show "Documents › Lightning › Mohab" and put the full path behind "Details".

## 4. Overview

### Summary

**[x] OV-1 · Flow · P1 — Phone order.** Phone order built (2026-10-14, owner approved C11.1 update). Remaining on PC: Needs you is first and folded to one line; the user cannot tell the count's urgency without opening it. Show the top item's words, its date and amount, and "+2 more".

**[x] OV-2 · Visual · P1 — Investments row is broken on PC.** "Portfolio value" floats to the far right as a title while the figure "177,903 · 6 holdings" is tiny on the left with a lone chevron. Lay it out as one KPI row: Portfolio value · Net gain or loss · Income collected · link.

**OV-3 · Logic · P2 — Three different "change" figures sit together.** Change in net worth +32,013, Net flow +26,341, Investing rate +18,450 money added. A user will ask why net worth rose more than they kept. This is the wealth-change bridge (M3.2): Net worth change = Kept (net flow) + Market moves + Other. Build it as the Change in net worth card's "Show the numbers". Highest-value missing answer on the Overview.

**OV-4 · Logic · P2 — "Month by month" shows one month.** The section is titled "Month by month · 2026-08 to today" and the left card's subtitle "Most in 2026-09 · 24,754", yet it draws October's day calendar. Either draw twelve month cells (as the right card does) or rename it "Day by day · 2026-10". Feedback row 64 also asked the right heatmap to show money out, not net flow.

**OV-5 · Logic · P2 — Free cash card repeats itself.** Free cash card and "How it is built" show the same three rows twice (feedback row 51). Keep the bar version; in the freed space show "Next out: WE Internet 650 on 2026-10-20".

**OV-6 · Logic · P2 — "If you sold today" hides why it is low.** 129,567 against What you own 253,462. The unfolded row explains a locked certificate, but folded it reads as a loss. Show "1 certificate locked until 2027-08-01" under the figure.

**OV-7 · Visual · P3 — Donut colours.** CDs (teal), Stocks (dark green) and Money market fund (light green) are three greens; Gold is brown. Use the A04 class colours and check that neighbours differ; feedback row 38 preferred a pie to the treemap, the donut already serves that.

**OV-8 · Feature · P3 — Net worth in dollars or gold grams.** After two devaluations many Egyptians judge wealth in USD or gold. A toggle under Net worth: "in EGP · in USD · in grams of 21K" using the dated rates the app already stores. No new data; large trust gain.

### Spending

**[x] SP-1 · Logic · P1 — Partial month compared with full months.** See X-4. The green "−25%" and "−22% against your usual month" mislead every day until the month ends. Same for the "Now against your usual month" bars (Food −30%, Other −90%).

**SP-2 · Visual · P2 — Treemap labels clipped.** "Eating 469 · 3%" and "Other 440 · 2%" are cut at the tile edge. Below a minimum tile size, list the category under the treemap instead.

**SP-3 · Visual · P2 — Calendars draw future days.** 15–31 October show placeholder dots. Leave future days blank; dots read as data.

**SP-4 · Logic · P2 — Loan payments counted as spending, with no switch to see it without them.** By decision a loan payment is spending. Fine, but the "Biggest" and "usual" comparisons then mix fixed commitments with choices. Add a filter chip "Without bills and loans" (the user's real question is "what did I choose to spend?").

**SP-5 · Feature · P2 — A merchant or category watchlist.** Open gap in Overview §5. Let the user pin up to four categories or counterparties (Talabat, Uber, Shopping); show them as small multiples at the top of Spending with this month against usual.

**SP-6 · Feature · P3 — Spending by account and by tag.** Today Spending answers by category only. "How much went through Vodafone Cash?" and "#ramadan" need a group-by choice (category · account · counterparty · tag).

**SP-7 · Logic · P3 — Refunds land in the wrong month.** Known (Mohab 13). Offer "Count it in the purchase month" when a refund is linked to its purchase.

### Health

**HE-1 · Logic · P1 — Savings rate disagrees with the Overview without saying why.** Overview 58.5% (October so far), Health 47.1% (September), both titled "Savings rate". Health should label "September (last complete month)" in the card title, not only in the chip.

**HE-2 · Visual · P1 — A line for one month.** Savings rate over time draws a diagonal from nowhere to 47.1% (see X-5).

**HE-3 · Logic · P2 — "Debt to cash" is a weak measure for a salaried borrower.** 69.5% compares all remaining car-loan payments (52,500) with cash today. Users understand "Loan payments to income" (5.6%) and "Months to debt-free" (21). Keep the ratio in "Show the numbers"; lead with the two that drive decisions.

**[x] HE-4 · Logic · P2 — Emergency fund ignores liquid holdings.** See RS-1. Show a second line: "Could also use: free cash 55,560 · money market fund 3,033 (days) · certificate locked".

**HE-5 · Visual · P3 — "4 of 5 within your limits" over seven rows.** Say "4 within, 1 below, 2 without a limit".

**HE-6 · Feature · P3 — Inflation check.** Egypt's inflation dwarfs most return figures. "Your net worth grew 18% in a year; prices rose 25%" is the single most useful health line for an Egyptian user. Needs a dated CPI series (CAPMAS) as a shipped file like the FX pack; see project #1.

### Currencies

**CU-1 · Flow · P2 — Empty page shows a period picker and three buttons.** "No accounts use another currency yet" under All time · YTD · Monthly · Custom, Accounts and Add account. Show one sentence ("Hold dollars or euros? Add the account and Lightning tracks what they cost and what they are worth") and one button that opens Add account with the currency field ready.

**CU-2 · Flow · P3 — Tab placement.** Currencies is an Overview tab but behaves like an account list. Once a user has foreign cash it is fine; while empty, hide the tab and offer it from Add account (one less tab for most users, frees the phone's fourth slot for Zakat, see OWNER 15).

## 5. Budget

**BU-1 · Flow · P1 — Changing one category's plan is hidden.** The per-category limits are typed inside "Spending by group" › Personal › fold › row. The visible "Spent of plan" bars have no way to edit. Make each bar row editable in place (click the "of 68" to type 100), and keep the group fold for bulk rules. (Roadmap B: "Change one category without the full grid".)

**BU-2 · Logic · P2 — Alarm out of proportion.** A full-width strong-rose card "Categories over plan 1 · Transportation" for 22 EGP over a 68 EGP plan. Scale it: under 5% or under 100 EGP over, show a dot on the row, not a card.

**BU-3 · Logic · P2 — Odd plan amounts.** Fill this month produces 68, 671, 1,480, 4,666, 15. Round fills to the nearest 50 (under 1,000) or 100, and let the user keep exact values.

**BU-4 · Logic · P2 — No pace.** At day 14 of 31, 76% used looks alarming, but 14,500 of it was rent and the loan on the 3rd and 5th. Show "Flexible spending: 4,159 of 10,199, on pace" separately from fixed bills that are already paid.

**BU-5 · Visual · P2 — "System Categories · Personal" in Spending by group.** Group names are the L1 tree, so the user sees "System Categories" with a "Personal" subtitle. Name it "Loan payments" (its only budgeted child) or "Bills and loans".

**BU-6 · Flow · P2 — Fill this month starts on an empty source.** "No base limits from last month are available to copy" while October has a plan. Open on the source that has data (Schedule or the current month) and say why another is empty.

**BU-7 · Feature · P2 — Next month's plan.** Open gap "a future month cannot be opened". Allow the month picker to go one month ahead and copy this month's plan into it.

**BU-8 · Feature · P2 — Give every pound a job (ready to assign).** Open gap. A single line under Planned: "Income 45,000 − Planned 24,699 − Goals 0 − Emergency top-up 10,417 = 9,884 not yet given a job" with "Assign" to a goal or a category. The Fill page already computes "9,884 EGP of room".

**BU-9 · Feature · P3 — Seasonal budget.** School fees (September), Ramadan, two Eids, summer trip. Suggest a reserve two months before, from last year's same month (after a year of data) or a built-in list of Egyptian seasons the user ticks.

**BU-10 · Visual · P3 — Settings page title.** The gear opens a page titled "Settings" with a full-screen icon and a second gear; it should be titled "Budget settings" with a back link to Budget. System categories (Internal transfers, Capital allocation, Adjustment) should not be offered as one-off choices.

## 6. Cash planning

### Plan

**[x] CP-1 · Logic · P1 — Two daily figures.** Safe to spend 39,103 "about 2,172 a day for 18 days" already subtracts Budget left to spend (4,910) and the emergency top-up, so it is money *beyond* the plan. Saying "a day" invites the user to spend 2,172 a day on top of a plan that allows 336. Change the line to "on top of your plan until 2026-11-01" and keep the per-day figure only on Budget.

**CP-2 · Logic · P2 — Safe to spend spends past savings.** Free cash includes everything kept in earlier months (75,560 cash), so Safe to spend grows every month a user saves and invites spending it. Offer the choice "Count only this month's money" (from income since the last payday) as a Budget setting, default unchanged **(owner)**.

**CP-3 · Logic · P2 — The gam'eya is missing from the next 30 days.** Needs you says an instalment is due and "In and out each month ahead" mentions a gam'eya payout, but the 30-day list shows bills, salary and the loan only. List instalments and the payout like any payment, with Mark paid.

**CP-4 · Visual · P2 — Empty left column.** The "From free cash to safe to spend" card leaves 400px empty under its five bars beside the long 30-day list. Put the forecast table or "What is promised?" there and shorten the page.

**CP-5 · Visual · P3 — Timeline labels.** "North Cairo Ele…" is cut; two labels collide when payments are close. Stagger labels or show amounts only, names on hover/tap.

**CP-6 · Feature · P2 — "Can I afford it?"** Open gap. A field on Plan: "If I spend [60,000] on [date]" redraws the forecast and says whether the lowest point stays above reserves. Read-only, nothing stored.

**CP-7 · Feature · P3 — Mark paid for a bill paid from another account.** Feedback row 37: settlement offered only the payroll account. Confirm every cash account is offered.

### Recurring

**[x] CP-8 · Visual · P1 — Sort by next date** (CP-4 in section 1 as #15).

**CP-9 · Visual · P2 — The same four bills listed twice.** "Bills and subscriptions" bars and "Recurring items" list repeat each other. Keep one list with a small bar per row, sorted by next date, income at the top.

**CP-10 · Feature · P2 — Suggested recurring items.** The Overview says recurring items are suggested; this tab shows no suggestion area for the sample (Talabat monthly, Mom 2,000 on the 25th, CIB fee 15 on the 28th are clear patterns). Show "Looks recurring: Mom −2,000 on the 25th · Track · Not recurring".

**CP-11 · Logic · P3 — Price changes.** Rent rises yearly, internet bills change. Offer "Amount changed from 650 to 700 since 2026-09: update the item?" when the matched payment differs by more than 5%.

### Loans

**LO-1 · Feature · P2 (owner) — Interest and total cost.** Loans have no rate, so "borrowed 60,000, 24 × 2,500" hides the cost (here 0% because the sample has none). Egyptian car and personal loans quote a *flat* rate; users cannot compare offers. Add an optional rate (flat or reducing) and show "Total interest" and "Cost of this loan". Still no interest accounting in the ledger: payments stay spending by decision.

**LO-2 · Feature · P2 — Pay off early.** Open gap. "Pay 20,000 now" on the loan page: shows new end date or new payment, records one transfer, re-plans the schedule. Optional early-settlement fee field.

**LO-3 · Feature · P2 — Instalment purchases (taqseet).** Phones, appliances and BNPL (valU, banks' card instalments) are loans with 0% and an admin fee. A "Bought in instalments" shortcut from Add transaction: price, months, fee, first date. Mohab step 22 already models one by hand.

**LO-4 · Visual · P3 — One loan, two summaries.** "Paid off on 2028-07-05" card, "Loans still to pay 52,500" card and the loan card all repeat. With one loan show only the loan card; the totals only from two loans.

### Reserves

**[x] RS-1 · Logic · P1 — Emergency coverage.** Spending default and optional income basis built (owner, 2026-10-14). Remaining: liquid-holdings context. Original evidence: Six months of income = 270,000 for a user who spends about 20,000 a month; 10,417 a month to reach it in two years. The usual rule is months of essential spending. The owner chose income on 2026-10-05; this review asks to reconsider: default to spending (fixed bills + usual flexible spending), or show both "4.6 months of spending · 0.4 of income". Also count what can be reached within a week (free cash, money market fund), separately from what is set aside.

**RS-2 · Feature · P2 — Refill reminder.** Open gap (Mohab 14). After a payment from the emergency fund, Needs you says "Emergency fund used 6,500 on 2026-10-18 · Refill over 3 months?".

**RS-3 · Feature · P2 — Where the reserve lives.** Reserves are earmarks with no account. Many users keep the fund in a separate savings account or a money market fund. Optional "Kept in: CIB Savings" makes Free cash exclude that account automatically and shows a mismatch when balances differ.

**RS-4 · Flow · P3 — Goal from a reserve.** "What are you saving for?" is empty with "Add a reserve below". Offer three one-tap starters for Egypt: Summer trip, School fees, Eid. Each asks only amount and date.

## 7. Investments

### Holdings

**[x] IN-1 · Logic · P1 — XIRR on short holdings.** See X-3.

**[x] IN-2 · Logic · P1 — Income outside return.** See section 1 #4. The certificate earns 18% but its Gain, Return and Net gain or loss are 0. Net gain or loss for the portfolio (+5,673) excludes 3,667 of interest received in the same months. Use total return everywhere: price change + gain from sales + income.

**[x] IN-3 · Logic · P1 — Sale factors and Holdings after sale disagree.** Settings › Sale factors lists CDs / Time Deposits 100,000 → 95,000 after sale; the figure counts the locked certificate at 0 (`planning/position.py` line 245). Show the lock in Settings, and **(owner)** decide whether a locked certificate counts at 0, at face less a break fee, or as "can borrow against it" (Egyptian banks lend against certificates).

**IN-4 · Logic · P2 — "Money and value by class" does not add up for a user.** October: Money in +18,450; Gold +23,595, Money market fund +3,033, Stocks +495. The fund was bought from brokerage cash, so it appears as growth while costing nothing new; the ring's purchase is inside Gold's +23,595. Split each class into "bought or sold" and "value moved" so Money in + value moved = change.

**IN-5 · Logic · P2 — Portfolio value "+46,703 since six months ago".** It counts new money (the ring, the shares and the fund bought since) as if it were growth, next to Net gain or loss +5,673. Split it: "+46,703: money added …, gain …".

**IN-6 · Visual · P2 — Horizon "Set" column.** Every row ends with "Set", a word that means nothing out of context (feedback rows 59–60 asked for S/M/L). Show S, M, L or "—"; set it on the holding page.

**IN-7 · Visual · P3 — Brokerage cash 400 is shown under Allocation** but is cash, not a holding. Move it to the Holdings table foot ("Cash at THNDR 400").

**IN-8 · Feature · P2 — Act from the holding.** The holding page has only "Investments" in its header. Add Buy more, Sell, Record dividend, Update price, with the account and asset filled in.

**IN-9 · Feature · P3 — Dividends calendar.** EGX dividends are announced; a user wants "COMI usually pays in April". After one year of data, list expected income by month.

### A holding

**[x] HL-1 · Visual · P1 — Worst month in rose while positive.** A16 "KPI by position". Tone follows sign.

**HL-2 · Logic · P2 — "Exposure Equity · Gain from sales in the period 0 · Dividends and interest in the period 0".** A raw line under Planning. Remove it or turn it into labelled rows.

**HL-3 · Visual · P3 — Two-point charts.** Price against what you paid, Value against cost and Fall from its high each have two points (X-5).

### Certificates (NBE CDs page)

**CD-1 · Feature · P2 — Expected interest, one tap.** Interest is "never posted automatically", so the user types 1,833 every month. Put "NBE interest 1,833 expected 2026-10-15 · Record" in Needs you on the payout day, filled in from the certificate. Lightning suggests, the user confirms: the same rule as salary.

**CD-2 · Flow · P2 — The purchase form has eleven fields.** Name, date, amount, from, rate, method, earliest withdrawal, maturity, term, payout schedule, compounding, payout account. Ask four (amount, rate, term in years, payout: monthly/quarterly/at maturity); derive maturity and lock-up from the term; put the rest under "More".

**CD-3 · Visual · P3 — Table wraps dates.** "2026-08- / 01" breaks across lines. Dates never wrap (`white-space: nowrap`).

**CD-4 · Feature · P3 — Maturity.** Open gap: "When does my certificate mature?" shows in the table, but nothing happens on the day. On maturity, Needs you: "NBE certificate matured: 100,000 back to CIB? · Renew".

### Planner

**PL-1 · Flow · P2 — Dead end without targets.** "Current target total: 0.00%" and a button to another page. Show three ready mixes (Cautious: 60% certificates / 20% gold / 20% shares; Balanced; Growth) the user can pick and edit here, or let them type targets inline. Never "0.00%".

**PL-2 · Logic · P2 — Amount starts at 10,000.** Start from Overview's "Plan to invest" figure (free cash above reserves and a month's spending) and say where it came from.

### Prices

**PR-1 · Visual · P2 — Four decimals everywhere.** "37,200.0000", "1.0000 pieces", "86.5000". Units: whole for pieces and certificates, as needed for shares and fund units; prices two decimals unless the instrument trades finer.

**PR-2 · Logic · P2 — Gold priced two ways.** Each gold piece has its own "New price per unit" field while 18K, 21K and 24K references also exist (18K and 24K "none"). Price pieces only from the karat reference (net weight × karat price), show the piece field as derived, and fill 18K and 24K from 21K by purity when missing (a typed price still wins).

**PR-3 · Flow · P3 — "Total value" and "New price per unit" side by side.** Two empty fields per row; the user does not know which to type. One field with a switch "per unit · total".

**PR-4 · Visual · P3 — "As of yyyy-mm-dd" label.** The format hint belongs in the placeholder, not the label.

## 8. Accounts

### Accounts

**AC-1 · Logic · P2 — Three names for one figure.** "In your accounts" (sidebar, Transactions), "Total balance" (Accounts), "In this account" (a register). The Glossary should own one name; the Accounts page uses it.

**[x] AC-2 · Logic · P1 — Unsigned transfers on PC.** See section 1 #5. Also "Vodafone Cash / Vodafone Cash" (counterparty and account repeated) on transfer rows: show "To Vodafone Cash" once.

**AC-3 · Visual · P2 — Sidebar lists only cash, bank and deposits.** "In your accounts 263,462.36" sits over a list that omits THNDR, Gold at home and the gam'eya, so the rows do not add to the total. List every account or say "Cash and bank" for the shown rows.

**AC-4 · Feature · P2 — Last activity and last check.** Add two quiet columns: last transaction date and "checked against bank on". A stale account (no import for 30 days) is the most common reason figures drift.

**AC-5 · Flow · P3 — Type names.** "Bank account (current or savings)", "Physical asset (gold and things you own)" in the table; use short types (Bank, Cash, Gold, Certificates, Brokerage, Gam'eya).

### A register

**RG-1 · Flow · P2 — No month breaks.** 40 rows in one table. Group by month with a month line (money in, money out, closing balance), and load older months on scroll.

**RG-2 · Flow · P2 — Check against bank is behind "More actions".** It is the action that keeps numbers honest; show "Check balance" as a header button with the last check date. OWNER 2.6 ("mark all checked up to this date") belongs here.

**RG-3 · Visual · P3 — Notes column mostly "—".** Show notes under the counterparty when present and drop the column.

**RG-4 · Logic · P3 — Category "Buy" on an investment purchase.** "L'Azurde ring · Buy · −18,450" reads like shopping. Show "Bought gold · Gold at home".

### Transactions and a transaction

**TX-1 · Visual · P2 — Raw timestamp and code.** The detail page's title is "BUY-2026-10-14-001" and "Recorded 2026-10-14T18:24:17+00:00". People see names, not codes (decision): title "L'Azurde ring · 2026-10-14", "Recorded 14 October 2026, 21:24 Cairo time"; keep the reference small under Details.

**TX-2 · Flow · P2 — Add transaction asks the account first.** "/accounts/add-transaction" is a list of accounts, then the form. Open the form with the last-used account selected and a switch.

**TX-3 · Feature · P2 — Bulk counterparty edit.** Still open (UX plan §8).

**TX-4 · Feature · P3 — Receipts.** Attach a photo to a transaction (stored encrypted in the profile, size-capped). Asked for in Competition (Lunch Money, Simplifi).

### Held for others

**HO-1 · Flow · P2 — No way to give it back from here.** The page lists "Mom · CIB Payroll · 10,000.00" and "How to record ownership". Add "Give back" and "Spend for them" on each row.

**HO-2 · Feature · P3 (owner) — The reverse: money others owe you.** Informal lending (سلف) between family and friends is common in Egypt and out of scope by decision. A "Lent to Ahmed 3,000 · due Eid" list, outside What you own until repaid, would answer a daily question.

### Zakat

**ZK-1 · Flow · P2 — Zakat day in Gregorian only.** "Pick the day each year… 354 days apart" with a yyyy-mm-dd field. Users know "1 Ramadan" or "the day I reached nisab". Offer "1 Ramadan this year" and show the Hijri date beside the Gregorian (Hijri not built: project #2).

**ZK-2 · Logic · P2 — Debts due now 0 with a loan running.** The common opinion deducts debts due before the zakat day (the next instalment, or the year's instalments by some). Show "Loan instalments due in the next 12 months 30,000 — deduct? (scholars differ)" as a switch, off by default.

**ZK-3 · Logic · P3 — Worn gold.** The ring is counted as "Gold held as savings". It may be worn; the worn flag exists on pieces but the user is not asked. When zakat is turned on, ask once per gold piece "Worn or kept as savings?".

**ZK-4 · Visual · P3 — Page jump covers "57,195".** X-1.

### Gam'eya

**[x] GA-1 · Logic · P1 — Joined late.** See section 1 #6. Today's page shows "0 of 10 paid", "Next instalment 2026-08-05", "Your turn 2026-10-05" and "Nothing owed either way". It should say "You owe 3 instalments (6,000) · The pot of 20,000 is due to you" and offer "Record past instalments" (one transfer per date) and "Record payout".

**GA-2 · Flow · P3 — "Account activity" and "More actions" lead.** The main actions (record instalment, record payout) are halfway down. Put "Pay instalment" and "Received the pot" in the header.

### Import and SMS

**IM-1 · Feature · P2 — CSV only.** Egyptian banks give PDF or Excel (project #17). Until then, save a column mapping per bank (CIB, NBE, Banque Misr, QNB) so the second import is one click, and say "5 MB" not "5 MiB".

**IM-2 · Flow · P2 — "Post ready rows" while undecided rows post as Unaccounted.** Still open (UX plan §8).

**IM-3 · Feature · P2 — Rule suggestions from filing.** Competition #3: after filing "Talabat → Eating Out" three times, offer a rule.

## 9. Settings and search

### Your data

**[x] SE-1 · Visual · P1 — Missing spaces around inline links.** Budget settings (see section 1 #13); check every `the same as <a>` pattern.

**SE-2 · Feature · P2 — Export everything.** "Export for AI" is the only export on the page. Add "Export all data (Excel and CSV)" first; it is the strongest answer to "data lost after a phone change" (Competition, users hate).

**SE-3 · Flow · P2 — Backup is a button with no history.** Show last backup time and place, how many are kept, and "Back up to another folder" (USB, OneDrive). Restore is Codex's claimed work (03a); this item is only the information line.

**SE-4 · Flow · P3 — Checkbox needs a Save.** "Show zakat" needs a separate Save; switches save on change elsewhere (categories). Same rule everywhere.

**SE-5 · Visual · P3 — "Show setup guide" floats above the card,** unaligned with the card grid.

### Categories

**CA-1 · Visual · P2 — Names cut.** "Capital alloc", "Internal tran". Let the name field size to its text; never cut a name (C03.3 says the same for tabs).

**CA-2 · Visual · P2 — Toggle state unclear.** Every expense shows a grey "One-off" pill and every income a grey or green "Recurring" pill. A grey pill looks like a label, not "off". Use a switch with the word, or show only the ones that are on.

**CA-3 · Logic · P2 — System categories can be archived or deleted.** Archive and Delete icons show on Internal transfers, Adjustment, Capital allocation, Loan payments, Money Held for Others, Zakat. Hide them; these carry rules.

**CA-4 · Feature · P2 — Egyptian categories.** The 35 starters miss what Egyptian salaried households spend on: Car (fuel, service, licence, insurance), Kids (school fees, private lessons), Domestic help, Building (doorman, maintenance), Charity and sadaqa, Mobile and internet top-ups. Offer them as optional packs at setup.

**CA-5 · Feature · P3 — Spending beside each category.** Show this month's and the usual amount next to each name, and merge two categories (moving their transactions).

### Counterparties

**CO-1 · Visual · P2 — "3 of the last 3" with no label.** The suggested-category column shows a confidence fraction alone; say "filed as Eating Out 3 of 3 times".

### Rules

**RU-1 · Flow · P2 — Empty list, no starters.** Offer two or three rules built from the user's own data ("Talabat → Eating Out", "Uber → Transportation") with Add.

### Data checks

**DC-1 · Logic · P2 — Words.** "What I own plus money held for others" (first person) beside "What you own" everywhere else; "pass" in lower case; "Gross account values should equal the asset-class breakdown". Lead with one line "All 8 checks pass" and fold the list; name failures in plain words with the fix.

### Search (Ctrl-K)

**[x] SR-1 · Visual · P1 — "Personal › Housing & Rent".** A16: "L1 › L2". Show "Housing & Rent" with "Personal" as a small label.

**SR-2 · Logic · P2 — "rent" finds the category but no transaction.** Rent is paid to "Landlord". Search should match category names in transactions too ("12,000 · Landlord · Housing & Rent · 2026-10-03"). See [search_matching.md](../7-planning-import-and-search/7D-search-and-matching.md).

## 10. Phone only

**[x] PH-1 · Flow · P1 — Needs you below the latest list** (OV-1).

**PH-2 · Visual · P2 — Chevrons drop under labels.** "Cash you own" then "›" on the next line; same for Over time, Free cash, What it is made of, Net flow. Feedback row 74 asked for arrows on the right, away from numbers.

**PH-3 · Flow · P2 — Overview is not one screen.** 2,636px tall against the decision "the Overview is one screen". Move Latest to Accounts (it already has five latest), and fold "This period" rows into the tiles.

**PH-4 · Visual · P3 — Letter avatars.** Rows start with "L", "M", "T" circles. A category icon or nothing would say more; letters repeat (Talabat and Toyota both "T").

**PH-5 · Flow · P2 — Add transaction is long for a cash spend.** Amount, counterparty, category, date, notes, then Save below the tab bar. Put the amount with a numeric keypad first, recent categories as four chips, "Save and add another", and remember the last account. Capture beats analysis (Competition compass 1).

**PH-6 · Visual · P3 — Budget hides categories.** The phone Budget shows only group totals and "Type a limit beside a category"; no category is visible to type beside until a group is opened. Open the group with an over-plan category by default.

## 11. Technical

**TE-1 · Tech · P2 — A screen review harness in the repo.** This review used a 90-line Playwright script (`profile_app`, sample household, every page at 1366 and 360, full-page images and visible text). `tools/phone_check.py` already does half of it. Extend it to `tools/screen_check.py --pc --phone --shots dir --text` so any AI can repeat a review in one command and diff screens before and after a change.

**TE-2 · Tech · P2 — Test the A16 list on rendered pages.** Today `test_docs_structure.py` keeps the list in sync with the guideline, but nothing checks screens. Cheap checks on rendered HTML of the main pages: no "›" between category names, no all-caps text nodes, no strong-rose class on a value with a plus sign, KPI figures without decimals, no element overlapping a right-aligned number at 1366 (Playwright bounding boxes).

**TE-3 · Tech · P2 — A rendered-text test for joined words.** SE-1 came from inline links without spaces. Scan visible text of all pages for a lower-case letter followed directly by a capital inside a word ("asRecurringon").

**TE-4 · Tech · P2 — Time zone.** "Recorded …+00:00" is UTC. Store UTC, show Africa/Cairo (`tzdata` is already a dependency).

**TE-5 · Tech · P3 — Two 318 KB stylesheets.** `style.css` and `style.rtl.css` are near copies (636 KB). Moving to logical properties (`margin-inline-start`) lets one sheet serve both; NOW.md Next 3 already lists a CSS trim.

**TE-6 · Tech · P3 — Speed with a real year.** On the three-month sample the Overview's first request takes 181 ms, other pages 8–64 ms (in-process, no browser). Measure the same pages on Mohab's 2026 (`/sample/mohab-2026`) and on three years of synthetic data before calling speed done; Transactions is already 73 KB of HTML for three months and will grow linearly without month paging (RG-1).

**TE-7 · Tech · P3 — XIRR guard.** Whatever the owner decides on X-3, the solver should return "not meaningful" rather than a number above, say, 1,000% or for under 30 days held, and the holding page should never show a three-digit annual rate without the holding period beside it.

**TE-8 · Tech · P3 — Gam'eya due logic in one place.** Needs you, the gam'eya page and Cash planning read the circle differently (GA-1, CP-3). One service method "what is due and owed on date D" used by all three, with a test for a circle joined after its start.

## 12. Decisions for the owner

Each is short; the item id leads to the detail.

1. **[x] XIRR under a year** (X-3): approved and built; plain return before 365 days, XIRR afterward.
2. **[x] Emergency fund basis** (RS-1): approved and built; spending by default, income optional. The liquid-holdings context in RS-1/HE-4 remains.
3. **[x] Locked certificate in "If you sold today"** (IN-3): approved and built; separate locked value and unlock date, excluded from saleable cash.
4. **Samples in their own profile** (FR-1): recommended yes.
5. **Pay-cycle months** (X-10): worth the size of the change?
6. **Safe to spend from this month's money only** (CP-2): offer the setting?
7. **Loan interest** (LO-1): an optional flat/reducing rate for cost display, still no interest in the ledger?
8. **Money others owe you** (HO-2) and **credit cards**: both out of scope by decision; informal lending is very common in Egypt. Reconsider the first?
9. **Zakat debts** (ZK-2): offer the "deduct instalments due this year" switch, off by default?

## 13. New features an Egyptian salaried user will ask for

**Milestone 1 built 2026-10-14:** FR-2 salary/payday; LO-2 early payoff (existing loan-category outflow, preserving the ledger contract); LO-3 instalment purchases; SE-2 full Excel/CSV export; IM-1 saved bank CSV presets and 5 MB wording. Existing screens only; PDF/Excel statement parsing remains unbuilt. Owner also approved dated historical loan repayments; cash records stay unchanged.

Beyond the open gaps already listed in the Project Overview, ranked by how often a real user would use them.

| Feature | Why | Size | Ids |
|---|---|---|---|
| Reminders (Windows and Android) | A user who does not open the app misses the bill | M | X-11 |
| Salary and payday at setup | Every tab works from day one | S | FR-2 |
| Expected-income and certificate-interest confirmations in Needs you | Two recurring manual entries become one tap each | S | CD-1, OWNER 2.2 |
| Wealth-change bridge | "Why did net worth change?" is the first question after the number | M | OV-3 |
| Net worth in USD or gold grams | How Egyptians judge wealth after devaluations | S | OV-8 |
| Inflation-adjusted view | Real growth, not nominal | M | HE-6 |
| Instalment purchases (taqseet, BNPL) | Phones and appliances bought on 6–24 months | S | LO-3 |
| Early loan payoff | Open gap | S | LO-2 |
| Ready to assign | Open gap | S | BU-8 |
| Seasonal budget (school, Ramadan, Eids, summer) | The months that break budgets | M | BU-9 |
| Export everything | Trust and portability | S | SE-2 |
| Egyptian category packs | Car, kids, domestic help, building, charity | S | CA-4 |
| Bank column presets for CSV, then PDF/Excel | Second import in one click | M | IM-1 |
| Receipts | Warranty and work claims | M | TX-4 |
| Lent to people | Informal family lending | M (owner) | HO-2 |

**Trust milestone completed 2026-10-15:** same-day Spending comparisons, total holding gains including income, signed two-decimal registers, atomic gam’eya catch-up, PC Overview preview/KPI row and separate emergency liquidity context. Phone readability report resolved after incorporating the current phone fixes.

## 14. Suggested order and Mohab steps

**Step 1 — trust (P1, about two sittings):** SP-1/X-4, X-3 display rule (after the owner), CP-1 wording, IN-2 total return, AC-2 transfer signs, GA-1, IN-3 label, X-1 button gutter, X-2 number helper, HL-1, OV-1/PH-1, SE-1, SR-1, CP-8 sort, OV-2 layout. Add TE-2 and TE-3 so they stay fixed.

**Step 2 — weekly friction (P2):** BU-1 edit in place, BU-2/3/4, CP-3 gam'eya in the 30 days, CD-1 interest confirm, RG-1 month breaks, RG-2 check balance, TX-1, TX-2, PH-5 quick add, IN-8 holding actions, PR-1/2, CA-1/2/3, HO-1, X-5 short-history charts, X-6 labels.

**Step 3 — features:** FR-2, X-11 reminders, OV-3 bridge, BU-8, LO-2/3, SE-2, OV-8, then the owner's choices from section 12.

**Mohab steps to add** (`tests/test_mohab_year.py`, each a strict `known_gap` until fixed):

- On 14 October, Spending's comparison with September uses the same days (SP-1).
- A share bought three weeks ago shows its return, not an annual rate above 100% (X-3).
- The NBE certificate's return includes its monthly interest (IN-2).
- A PC register row for a transfer out reads "To …" with a minus (AC-2).
- He joins a gam'eya that started two months ago: the circle page says what he owes and records the past instalments in one step (GA-1).
- Budget's daily figure and Cash planning's line do not contradict each other (CP-1).
