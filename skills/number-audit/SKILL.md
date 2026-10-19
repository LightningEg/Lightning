---
name: number-audit
description: Prove that Lightning's figures agree with the ledger and with each other, before and after a change to financial code or a write path. Use after changing money logic, import, plans, budgets or reports, or whenever a number looks wrong.
---

# Number audit

Tool-neutral. Money figures must be right before anything else: a wrong figure outranks every layout wish. Financial calculations live in Python services, never templates or JavaScript.
Name the period or date of every figure you compare; most "mismatches" are two different periods.

## Token rules

Do the arithmetic with SQL and a few lines of Python, not by reading pages twice. Print only the differences. Fetch pages with `curl`/`urllib` and pull the figure you need.

## Set up

`python -m lightning --demo --no-browser` (port 8766; rebuilt on every start; never real data). The database is `data/demo.db`. Ledger columns you need:
`ledger_entries(account_id, asset_id, quantity_e6, amount_base_e6, effect, category_id, date, transaction_id)`; amounts are integers in millionths. `effect` is one of
`OPENING, INFLOW, OUTFLOW, INTERNAL, REVALUATION`. A second source of truth: `tests/test_audit_numbers.py` and `tests/test_mohab_year.py` (read only their docstrings).

## Invariants to check

Run them as a script that prints the differing lines. Whole-EGP displays round **half up** (a figure of 468.50 shows as 469 everywhere).

1. **Every transaction balances.** For each transaction, internal (transfer) lines sum to 0: `SELECT transaction_id, SUM(amount_base_e6) FROM ledger_entries WHERE effect='INTERNAL' GROUP BY transaction_id HAVING SUM(amount_base_e6)<>0`.
2. **Cash accounts:** displayed balance = `SUM(amount_base_e6)` of that account's ledger lines (cash, bank, wallet). Investment, gold and certificate accounts show *value* (units × price), which can differ from ledger cost: compare those with Investments instead.
3. **Sidebar total = Accounts page total = sum of the account rows.** "What you own" = total − money held for others (`/money-from-others`).
4. **Net worth** = what you own − what you owe (loans still to pay). It excludes money held for others. Change in net worth over a period = net flow + revaluations + investment gains; the three pieces appear on the Overview and Investments.
5. **Net flow** = money in − money out for the same dates. **Savings rate** = net flow ÷ money in. **Investing rate** = money added ÷ net flow. Overview, Spending and Budget use the same `money out` for the same period.
6. **Budget:** planned − spent = left, per category and in total; planned total = sum of the categories; "Plan leaves to save" = average monthly income − planned.
7. **Cash planning:** free cash = cash you own − reserves − bills due; safe to spend = free cash − bills and loan payments before next income − budget left to spend − emergency top-up; per-day figure = safe to spend ÷ days to the next income.
8. **Financial health:** each ratio recomputes from the figures printed beside it (emergency fund = reserves ÷ average monthly income, debt to net worth, fixed costs to income, loan payments to income).
9. **Investments:** holdings total = sum of the rows = the Overview "Holdings value"; allocation shares sum to 100%; gain = value − cost; a return over less than a year is a plain percentage, not annualised.
10. **Charts and tables agree:** the "Show the numbers" table under a chart equals its drawing; a tooltip equals its row.

## Move-it test (the strongest check)

For each write path, record the invariants, perform one change, and check **every tab moved by exactly that amount and no other figure moved**:
add an expense, an income, a transfer between own accounts, an investment buy and sell, a bill marked paid, a loan payment, a CSV import row, a reconcile adjustment, a delete then restore of a transaction, a budget change.
Then repeat each with edge amounts (cents, very large, zero is refused, negative is refused) and a **double submit** (the second must be refused or harmless). Record the paths and amounts you used.

## If a figure is wrong

Find the single source: grep the figure's label in `lightning/ui/templates`, follow it to the route and the service (`lightning/reporting`, `lightning/planning`, `lightning/budgeting`, `lightning/investments`). Fix it there once, add a test that fails before and passes after, add a Mohab step if a person would have seen it,
and say in the changelog which screens changed. Never patch a number in a template.

## Report

**Where findings go.** Read `issues/README.md` once. Fix a small finding now (branch, test, changelog line) and file **no** item. File anything bigger as one item in
the milestone it belongs to, `issues/<n>-<name>/<code>-<what>.md` (code from `python tools/issues.py next <n>`; this skill's name in `skills`, your model in `by`, `app_version`
from `pyproject.toml`, `commit` from `git rev-parse --short HEAD`), then run `python tools/issues.py`. Finishing an item means deleting its file in the same commit and adding its code to the milestone's `done:`. Never leave a finding only in chat.

A table: invariant, expected, found, result. List each mismatch with the page, the period, both values, and the cause (`file:line`) when known. End with the write paths you tried and what you did not check.
