# Audit 17: one figure, one owner - do the PC and the phone show the same numbers, and can a screen work one out itself?

Date: 2026-11-09 · Author/reviewer: Claude
Repository: app · Reviewed commit: 90f01900587841fa8fdea859fbf9f2cc8314140a
Code: r36 · App version: 2.1.2

## Assessment

**The ledger figures are sound and agree everywhere.** On two households, Net worth, What you own, What you owe, In your accounts, Free cash, Safe to spend, Money in and Money out are the same number on every PC and phone page that shows them, and one expense of 123 moved every figure by exactly 123 and a transfer moved none.

**The faults are all in figures a screen works out for itself.** Five were found; four are on screens built in the last two weeks. Each is a place where UI code adds or subtracts money instead of asking the service the Glossary names:

1. Phone Budget's "Where the month went" counts fixed costs twice: 33,851 "Spent" in a month whose Money out is 19,001.
2. Phone Money's change this month is worked out in the screen and is wrong: −10,438 where the PC's Overview says +36,395.
3. The Investments Lead draws "Cost 325,088 · Unrealized gain +27,399" under a Portfolio value of 752,486: the working does not add up to the figure.
4. The payday proposal's lines overlap: Bills protected sits inside "Everyday spending", so the lines add up to more than the cash they share out.
5. Three names carry two figures each: Left in plan, Everyday spending, Kept.

**Why they got through.** The rule exists (Glossary: "never computed a second way"; Architecture › Figures layer) but its guard, `tests/test_figures_layer.py`, only checks that drawing code and routes do not read the database. It does not look at arithmetic, and it does not look at `lightning/ui/phone/screens/`, `kpis.py`, `status.py` or the templates at all. Nothing compares the PC with the phone.

## Owner direction (asked in this session, 2026-11-09)

"Left in plan" keeps its Glossary meaning (Planned − Spent, 6,598 in the demo) on every screen. The phone's Budget keeps leading with everyday money (5,468) under its own name, **"Left for everyday"**, a figure with its own registry row.

## Scope and method

- **One database, two apps.** `evidence/harness.py` builds a household in a temporary database on a pinned day, renders 19 PC pages and 21 phone pages over it (the phone with its own router mounted, as `profile_app(phone=True)` does), and lists every registry label that shows more than one value. Run on the demo household (2026-11-09) and Mohab's sample year (2026-10-21).
- **Owner values.** `evidence/owners.py` calls the functions the registry names (`PositionService.at`, `change_in_net_worth`, `cash_flow`, `plan_summary`, `everyday`) and prints their values to compare with the pages.
- **Move-it.** `evidence/moveit.py` records one expense, then one transfer, of 123 and reads 24 headline figures on both surfaces before and after.
- **Static.** An AST count of `+ − × ÷` and `sum()` in `lightning/ui/**/*.py`, read line by line in the phone screens, `kpis.py`, `keynotes.py`, `status.py` and seven route files; a count of arithmetic in templates.

## Invariants

| Invariant | Demo, 2026-11-09 | Sample year, 2026-10-21 | Result |
| --- | --- | --- | --- |
| Net worth: PC Overview = PC Limits = phone Money = phone Limits = `Position.net_worth` | 198,821 | 909,064 | pass |
| What you own: PC Overview = PC Accounts = phone Money = `Position.what_you_own` | 265,321 | 988,804 | pass |
| What you owe, same pages and `Position.what_you_owe` | 66,500 | 79,740 | pass |
| In your accounts: PC Accounts = phone Accounts "Total" = `Position.in_your_accounts` | 261,321 | 981,704 | pass |
| Free cash: PC Overview = PC Cash planning = phone Home = phone Cash planning | 67,018 | 147,961 | pass |
| Safe to spend: PC Overview = PC Cash planning = phone Home = phone Cash planning | 51,420 | 114,288 | pass |
| Money out this month: PC Overview = Compare = phone Report = phone Activity = `cash_flow` | 19,001 | 3,410 | pass |
| Left in plan: PC Overview = PC Budget = phone Home = `plan_summary["left"]` | 6,598 | 35,018 | pass |
| Left in plan on phone Budget | 5,468 | 16,558 | **fail** (F3: another figure under the name) |
| Change in net worth this month: PC Overview = phone Money = `change_in_net_worth` | +36,395 / −10,438 | +33,350 / −16,650 | **fail** (F2) |
| Phone Budget donut total = Money out | 33,851 / 19,001 | 3,410 / 3,410 | **fail** (F1; the sample has no fixed cost paid that month) |
| Investments Lead: Cost + Unrealized gain = Portfolio value | not read | 352,487 / 752,486 | **fail** (F4) |
| Payday proposal: its lines = Cash available to assign | 67,018 / 67,018 | 133,201 + 15,740 / 117,461 | **fail** (F5) |
| One expense of 123: every watched figure moves by 123 or 0 | 24 of 24 | not run | pass |
| One transfer of 123: nothing moves | 24 of 24 | not run | pass |

## Findings

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | medium | **Phone Budget, "Where the month went": 33,851 Spent; Money out that month is 19,001.** `spend_donut(rows, paid)` adds a "Fixed costs" slice (14,850 paid) to category slices that already hold those payments (Housing & Rent 12,000, Loan payments 2,500, Utilities 350). Expected: the total is Money out in the plan's categories; fixed costs are either one slice with the categories net of them, or not a slice. | [demo pages](evidence/demo-pages.json) `phone:/budget/flexible`; `lightning/ui/phone/screens/budget.py:122` | BV-12O (fixed: `tests/test_phone_budget_flexible.py`) |
| F2 | medium | **Phone Money: "−10,438 since the start of the month"; the PC's Overview, same profile and day: "+36,395".** The screen subtracts `position.at(day 1)` itself (`money.py:104`); the registry's owner is `PositionService.change_in_net_worth`, which the PC calls and which counts from the day before the start. r35 F1 found the sentence; this is its cause and the right fix. | `owners.py`: `change_in_net_worth(2026-11-01, 2026-11-09) = 36,395`; [demo pages](evidence/demo-pages.json) `phone:/money`, `pc:/` | BT-11K fixed in [PR #478](https://github.com/LightningEg/Lightning/pull/478); [month-start regression](../../../tests/test_phone_money.py) |
| F3 | medium | **"Left in plan" is two figures.** Glossary: Planned − Spent, "the Overview and Budget show the same month figure". PC Budget, PC Overview and phone Home show 6,598; phone Budget shows 5,468 under the same name, worked out in the screen (`budget.py:71`) though `EverydayBudget.everyday_left` already holds it. r35 F2 read this the wrong way round (it took the phone's Budget as the reference). Decided: see Owner direction. | [demo pages](evidence/demo-pages.json) `pc:/budget`, `phone:/budget/flexible`, `phone:/home` | BV-11L1 fixed; [registry-label regression](../../../tests/test_phone_budget_flexible.py) |
| F4 | medium | **Investments Lead: the bar and line under Portfolio value 752,486 say Cost 325,088 and Unrealized gain +27,399.** The route subtracts custody cost and value itself (`routes/investments.py:128-129`) from the investment report, which leaves out holdings the Portfolio value counts (a 400,000 flat). The table below says Cost 725,088. Expected: the Lead's parts add up to the Lead, from one function. | [sample pages](evidence/sample-pages.json) `pc:/investments`; `lightning/ui/routes/investments.py:128`, `:211` | BT-12AC fixed; [lead adds up](../../../tests/test_investments_lead_adds_up.py) |
| F5 | medium | **Payday proposal: the lines do not add up, and one is misnamed.** Sample year: Bills protected 15,740, "Everyday spending" 35,018, Emergency and goals 98,183, Left unassigned 0, under "Cash available to assign: 117,461 → 0". The spending line already contains the protected bills (`funding.py:86-89`), so 35,018 + 98,183 is 15,740 more than the cash. "Everyday spending" is the registry's name for what was spent so far (3,410), not what the plan is given. r27 J4 called this ambiguous; this is why. | [sample pages](evidence/sample-pages.json) `phone:/payday`; `lightning/planning/funding.py:86`, `:117` | BT-12AD fixed; [proposal adds up](../../../tests/test_payday_proposal_adds_up.py) |
| F6 | low | **"Kept" is two figures and is not in the registry.** Phone Report: "Kept +27,833" (Net flow). PC Spending's flow chart: "Kept 25,832 · 55%" for the same month (Net flow less what was invested). The Overview's sentence "You kept 59%" uses the first. | [demo pages](evidence/demo-pages.json) `phone:/money/report`, `pc:/birdview/expenses` | [IT-12AE](../../12-desktop-ux/IT-12AE-a-screen-cannot-work-out-money.md) step 12AE5 |
| F7 | medium | **The figures rule has no working guard.** `tests/test_figures_layer.py` (3 tests) checks database reads in `visuals.py`, `charts.py`, `keynotes.py` and `routes/`. Not checked: arithmetic anywhere; `phone/screens/` (53 arithmetic sites), `kpis.py` (54), `status.py`, templates (11 expressions in 4 files). Read line by line, at least 45 lines in the UI layer derive a money figure: for example `kpis.py:183` (`left = planned - spent`), `:223`, `:228`, `:307`, `dashboard.py:392`, `planning.py:330-374`, `reserves.py:71` (the Refill amount, r24 F3), `keynotes.py:162` (a second "a day" formula, still reachable from `routes/budget.py:297`). Most are harmless differences of two owner figures today; F1 to F4 are what the same habit produced on new screens. | the AST count in Validation; `tests/test_figures_layer.py` | [IT-12AE](../../12-desktop-ux/IT-12AE-a-screen-cannot-work-out-money.md) |

## The design: how a screen is stopped from working out money

Three small things, in IT-12AE, none of them a rewrite:

1. **Derived figures move to their owners.** Each of the lines in F7 becomes a property or method beside the figures it combines (`Position`, `EverydayBudget`, `ForecastMonth`, the budget summary), with a registry row when it has a name on screen.
2. **A ratchet, not a ban.** A test counts money arithmetic per UI file (the AST scan of this audit, drawing code excepted by an explicit marker) against a committed list. The count may only fall. A new screen starts at zero.
3. **The two apps are compared.** The harness of this audit becomes a test: on the demo household and Mohab's year, every registry label shows one value across PC and phone for one period, and each "parts of a whole" (a donut, a proposal, a Lead's bar) adds up to its whole.

## Validation and limits

- `python issues/11-phone-ux/r36-figures-one-owner/evidence/harness.py demo 2026-11-09 OUT.json` and `... sample 2026-10-21 OUT.json`: 40 pages each, all HTTP 200; the page text is in [demo-pages.json](evidence/demo-pages.json) and [sample-pages.json](evidence/sample-pages.json).
- `python .../evidence/moveit.py demo 2026-11-09 expense` and `transfer`: 24 of 24 as expected.
- AST count of arithmetic sites in `lightning/ui` (i18n left out): `charts.py` 233 and `visuals.py` 87 (drawing), `routes/budget.py` 109, `routes/investments.py` 77, `kpis.py` 54, `routes/birdview.py` 42, `routes/dashboard.py` 35, `routes/analysis.py` 34, `phone/screens/` 53. `routes/budget.py`, `routes/investments.py`, `birdview.py` and `analysis.py` were counted, not read line by line.
- Not checked: JavaScript (whether any script does money arithmetic), charts against their "Show the numbers" tables, Financial health ratios, zakat, foreign currency and investment returns, longer periods (YTD, All time), Arabic digits, the other write paths of the move-it test (buy, sell, bill paid, loan payment, import, delete and restore), edge amounts and double submits. The sample-year move-it was not run.
- The label matcher is rough: it lists many differences that are two periods or a row under a heading. Every finding above was read in context and traced to code; nothing is reported from the matcher alone.
- No app code changed.

## Dated follow-ups

