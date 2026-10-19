---
name: bug-hunt
description: Run Lightning on the demo data, try every page, button and form, reconcile the figures across tabs, and report bugs with evidence. Use when asked to test the app, hunt for bugs, or check that numbers match.
---

# Bug hunt

Tool-neutral. Report only what you reproduced. Fix nothing until the owner chooses (each fix gets its own branch, a test and a changelog line).

## Token rules

Use `curl` and scripts for everything that is not visual. Open a browser only for layout, charts and JavaScript. Grep before reading code.
Reconcile with SQL on `data/demo.db`, not by reading pages twice. Print only differences.

## Steps

1. **Start the app:** `python -m lightning --demo --no-browser` (port 8766, rebuilt on every start; never your real data).
2. **Crawl:** `python tools/bug_crawl.py` lists pages that fail (not 200), lack a title or show broken text (`None`, `nan`, a template tag, a long decimal).
3. **Reconcile numbers** (a wrong figure outranks any layout wish). Check each pair, with the period named:
   - sidebar total = Accounts page = ledger sum per account (`SELECT SUM(amount_base_e6) FROM ledger_entries GROUP BY account_id`), allowing for held-for-others money;
   - Overview net worth = what you own − what you owe; its Net flow = money in − money out; savings rate = kept ÷ money in;
   - Budget spent and left = Spending money out = Overview; Cash planning's Safe to spend arithmetic (free cash − bills − budget − top-up);
   - Health ratios recompute from the figures printed beside them; Investments totals = sum of holdings.
   Then change something (add a payment, a transaction) and check every tab moved by exactly that amount.
4. **Exercise the forms** by direct posts: valid input, then blank, zero, negative, letters, huge, two decimals+, bad date, future date, wrong account type, an unknown id.
   Also post the same form twice (double submit) and confirm the second is refused or harmless.
5. **Browser pass (visual only):** every page at 1280 px and 390 px wide: JavaScript errors, failed requests, sideways overflow, buttons that do nothing.
6. **Suite:** run the full tests and compare the failures with the last run; a new failure is a finding. Environment failures (for example a missing module) are listed once, not per test.

## Report

**Where findings go.** Read `issues/README.md` once. Fix a small finding now (branch, test, changelog line) and file **no** item. File anything bigger as one item in
the milestone it belongs to, `issues/<n>-<name>/<code>-<what>.md` (code from `python tools/issues.py next <n>`; this skill's name in `skills`, your model in `by`, `app_version`
from `pyproject.toml`, `commit` from `git rev-parse --short HEAD`), then run `python tools/issues.py`. Finishing an item means deleting its file in the same commit and adding its code to the milestone's `done:`. Never leave a finding only in chat.

One line per bug: severity (high = wrong money or lost data, medium, low), where, what you did, what happened, what should happen, `file:line` of the cause when known.
Close with what you checked and found fine, and what you could not check. Stop the demo server when done.
