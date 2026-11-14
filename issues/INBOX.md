# Inbox

Things seen, not yet planned. One line each: date, pillar, what and where (a page, a file, a test). Rules:
[AGENTS.md](../AGENTS.md) section 3.

- A line costs nothing and promises nothing. It becomes an item only when someone starts it or the owner picks it.
- Fixed in the same sitting? Fix it and delete the line; it never needs an item.
- Wrong money or lost data is never a line: it gets an item at once.
- Lines older than 30 days that nobody picked are deleted in the next plan sweep.

## Lines
- **Browser View Transition rejection (build, 2026-11-13):** `test_pc_period_browser.py::test_pc_period_track_submits_months_and_custom_ranges` reports "Transition was aborted because of invalid state. Page already revealed" on a clean `cef6b629` checkout as well as IT-3BI4; inspect transition promise handling without weakening the page-error assertion. Confirmed again on clean main `fc02b41a` with Chromium 156 during IV-3BH5 (2026-11-14): an isolated pass followed by the same Page already revealed rejection.
- **C2 (from IV-3AM, 2026-11-12):** Cash planning's *What you owe* card stands alone in its row with one loan; pair it or make it a row (IV-12Q gave the unfinished Budget and Cash pages their pattern but left this page alone). Report: r19 C2.
- **Rose on dark cards (from NF-10C3, 2026-11-12):** the app's rose `#C93D72` (`--rose`, `--neg`) reads about 3.8:1 on every dark theme card; give it a `--theme-rose` the way `--theme-positive` and `--theme-held` are made in `tools/build_themes.py`.
- **Popup fields at 15px on the phone (Add sheet review, 2026-11-12, capture):** inside the phone's sheets (outside `.main`) Who, Date, Notes and the account select are 15px, not the 16px C05.1 asks for so the phone does not zoom; the `.main`-scoped field rule in phone.css never reaches them.
- **Theme motion, what is left (feel, 2026-11-13, after the phone header moved to the compositor):** Papyrus keeps `backdrop-filter: blur(14px)` on the sticky phone bar; measure scrolling on a real phone before keeping or dropping it (owner, 2026-11-13). The PC `.topbar` threads (`m-thread`, `m-pigment`) still move a background and repaint, but that bar is not sticky; same transform recipe if it shows up in a PC profile.
- **Move plan dialog, Arabic (plan, 2026-11-13, from #626):** the PC dialog's preview line (`budget_move.html`, `'{to} {a} → {b} · {from} {c} → {d}'|tr`) shows category names in English on the Arabic screen ("Food & Groceries من 3,000 إلى 4,650"); the heading above translates them.
- **`issues.py next` reuses a done code (build, 2026-11-13):** `python tools/issues.py next 12` printed `12AF`, already in folder 12's `done:` as `BV-12AF`; it should skip codes listed under `done:` with their tag.
- **Payday proposal parts (plan, 2026-11-14, r37 W8):** `/payday` shows "Bills protected 0 EGP" above two bills due before payday (they sit in "To your plan").
- **Loans: two totals (plan, 2026-11-14, r37 W9):** `/plan/loans` leads "52,500 left to pay" and its ratios say "66,500 owed"; the 14,000 gam'eya is named only on Plan.
- **Past free cash moves (plan, 2026-11-14, r37 W10):** a bill added today with past due dates changes September's and October's month-end free cash on Plan's chart.
- **Goals worded as bills (plan, 2026-11-14, r37 L4):** a savings goal on `/plan/reserves` reads "Upcoming payment", "Link or review a payment", "Match by: Ask"; saving answers "Most you can plan this month is now 36,000".
- **Budget until payday (plan, 2026-11-14, r37 L5, L6):** the label covers the rest of the calendar month and whole future months in the forecast table; *Lowest point ahead* repeats Safe to spend on Plan in the usual month.
- **The next 30 days (plan, 2026-11-14, r37 L7, P5):** capped at seven rows with gam'eya always last, out of date order; "3 more · Recurring" links to a page without loans (Upcoming has them).
- **Catch up and duplicates (plan, 2026-11-14, r37 P2, P3):** late payments go one at a time with no "all paid"; the same income added twice is accepted without a word.
- **Two loan forms (plan, 2026-11-14, r37 P4):** *Add loan* and *Bought in instalments* make the same plan from different fields; the second reads as the heading over every loan.
- **Planning form polish (feel, 2026-11-14, r37 P6-P8):** radio circles show above the Type pills in the add popup; ".00" and raw "−60000 EGP" amounts (A16); the "Scheduled cash checks" card's wording; *In and out › Show the numbers* is clipped at 1366 px.
- **Loan as its payments (own, 2026-11-14, r37 M5):** a loan of 80,000 repaid as 36 x 3,000 lowers net worth by 108,000 when added; for the owner's eye.
- **Bill changes once (plan, 2026-11-14, r37 M3):** the scenario moves one occurrence; a rent rise that stays cannot be tried.
