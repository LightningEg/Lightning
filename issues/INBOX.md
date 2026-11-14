# Inbox

Things seen, not yet planned. One line each: date, pillar, what and where (a page, a file, a test). Rules:
[AGENTS.md](../AGENTS.md) section 3.

- A line costs nothing and promises nothing. It becomes an item only when someone starts it or the owner picks it.
- Fixed in the same sitting? Fix it and delete the line; it never needs an item.
- Wrong money or lost data is never a line: it gets an item at once.
- Lines older than 30 days that nobody picked are deleted in the next plan sweep.

## Lines
- **Local xdist worker exit (build, 2026-11-14):** on Python 3.13.5, the six-worker #653 run lost `gw2` during `test_mohab_phone.py::test_the_whole_year_is_lived_on_the_phone_with_only_the_known_detours` and later stalled in browser cleanup (4,462 passed, 12 skipped before interruption); that test plus the active browser modules passed all 13 tests in one process. Investigate the process exit if it recurs; current-head CI remains required.
- **Browser View Transition rejection (build, 2026-11-13):** `test_pc_period_browser.py::test_pc_period_track_submits_months_and_custom_ranges` reports "Transition was aborted because of invalid state. Page already revealed" on a clean `cef6b629` checkout as well as IT-3BI4; inspect transition promise handling without weakening the page-error assertion.
- **C2 (from IV-3AM, 2026-11-12):** Cash planning's *What you owe* card stands alone in its row with one loan; pair it or make it a row (IV-12Q gave the unfinished Budget and Cash pages their pattern but left this page alone). Report: r19 C2.
- **Rose on dark cards (from NF-10C3, 2026-11-12):** the app's rose `#C93D72` (`--rose`, `--neg`) reads about 3.8:1 on every dark theme card; give it a `--theme-rose` the way `--theme-positive` and `--theme-held` are made in `tools/build_themes.py`.
- **Popup fields at 15px on the phone (Add sheet review, 2026-11-12, capture):** inside the phone's sheets (outside `.main`) Who, Date, Notes and the account select are 15px, not the 16px C05.1 asks for so the phone does not zoom; the `.main`-scoped field rule in phone.css never reaches them.
- **Theme motion, what is left (feel, 2026-11-13, after the phone header moved to the compositor):** Papyrus keeps `backdrop-filter: blur(14px)` on the sticky phone bar; measure scrolling on a real phone before keeping or dropping it (owner, 2026-11-13). The PC `.topbar` threads (`m-thread`, `m-pigment`) still move a background and repaint, but that bar is not sticky; same transform recipe if it shows up in a PC profile.
- **Move plan dialog, Arabic (plan, 2026-11-13, from #626):** the PC dialog's preview line (`budget_move.html`, `'{to} {a} → {b} · {from} {c} → {d}'|tr`) shows category names in English on the Arabic screen ("Food & Groceries من 3,000 إلى 4,650"); the heading above translates them.
- **`issues.py next` reuses a done code (build, 2026-11-13):** `python tools/issues.py next 12` printed `12AF`, already in folder 12's `done:` as `BV-12AF`; it should skip codes listed under `done:` with their tag.
