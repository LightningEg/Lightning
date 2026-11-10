---
title: A screen cannot work out money - derived figures move to their owners, a ratchet test counts arithmetic in the UI, and the PC and phone are compared on one household
type: tech
pillar: build
size: L
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: number-audit
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r36 F6 and F7 ([report](../11-phone-ux/r36-figures-one-owner/report.md)). The rule is written (Glossary: every figure has one function and "is never computed a second way"; Architecture › Figures layer) but `tests/test_figures_layer.py` only checks that drawing code and routes do not read the database. It does not look at arithmetic, at `lightning/ui/phone/screens/`, `kpis.py`, `status.py` or the templates, and nothing compares the PC with the phone. Four wrong figures reached the screen that way (BT-11K, BV-12O, BT-12AC, BT-12AD), three of them on screens two weeks old.

Money arithmetic found in the UI layer (line numbers at commit 90f0190):

- `phone/screens/budget.py` 71 (left), 87 (gap), 101 (paid), 122 (donut); `phone/screens/money.py` 82, 105 (since), 114 and 132 (accounts total).
- `kpis.py` 139, 146-150, 183 (`left = planned - spent`), 223, 228, 251, 293, 307, 318, 340, 424, 437, 452.
- `keynotes.py` 98, 162 (a second "a day" formula, reached from `routes/budget.py:297`), 202-210; `status.py` 58, 124.
- `routes/dashboard.py` 392; `routes/planning.py` 273, 281, 330-374, 706, 713; `routes/reserves.py` 30-31, 71-92, 159; `routes/accounts.py` 116-139, 180; `routes/investments.py` 128-129.
- Counted, not read: `routes/budget.py` (109 sites), `routes/investments.py` (77), `routes/birdview.py` (42), `routes/analysis.py` (34); 11 arithmetic expressions in 4 templates.

Names used for two figures: "Kept" (phone Report: Net flow; PC Spending's flow chart: Net flow less invested; not in the registry), "Everyday spending" (BT-12AD), "Left in plan" (BV-11L1).

## Fix

Three guards, in this order, so the tests exist before code moves. No screen changes its look.

## How to work on this item

One PR per step. Money moves into the service that owns its inputs (`lightning/planning`, `budgeting`, `reporting`, `investments`), never into another UI module. A figure with a name on screen gets a registry row in `lightning/core/figures.py`, then `python -m lightning.core.figures` regenerates the Glossary. After each step: `python -m pytest -q tests/test_figures_layer.py tests/test_audit_numbers.py tests/test_mohab_year.py tests/test_mohab_phone.py`, and pages must be byte-identical unless the step says a figure was wrong. Stay out of `lightning/ui/journal*` (claimed). Delete the step's heading in the same commit.

## 12AE1 The PC and the phone are compared on one household · M · opus
A new `tests/test_figures_agree.py` from `issues/11-phone-ux/r36-figures-one-owner/evidence/harness.py`: one database, the PC app and the phone app (`mount_phone`), the demo household and Mohab's year on pinned days. For a fixed list of (label, page, period) it asserts one value across both surfaces and equality with the owner function: Net worth, What you own, What you owe, In your accounts, Free cash, Safe to spend, Money in, Money out, Left in plan, Change in net worth this month. Known failures (BT-11K, BV-11L1) are strict `xfail` with their codes until fixed. Read values through `data-fig="<registry key>"` attributes added to those elements, not by text position.

## 12AE2 Parts add up to their whole · S · sonnet
In the same test file: every donut, split bar and proposal on the main pages sums to the figure it sits under (phone Budget donut = Money out in plan categories, What you own by kind = What you own, the Investments Lead, the payday proposal, Safe to spend's rows). BV-12O, BT-12AC and BT-12AD are strict `xfail` until fixed.

## 12AE3 A ratchet on arithmetic in the UI · M · opus
`tests/test_figures_layer.py` gains an AST count of `+ − × ÷` and `sum()` per file in `lightning/ui` (not `charts.py`, `visuals.py` or i18n; a line that is geometry, a count of rows or a date carries `# not money` and is skipped). The counts live in a committed file; a file's count may fall, never rise, and a file not listed must be zero. Done when adding `a - b` to a phone screen fails the suite.

## 12AE4 Derived figures move to their owners · L · opus
Work down the list in the Report, one service at a time (position, budget and everyday, forecast, reserves, loans and recurring, accounts, investments), lowering the ratchet as each goes. Each becomes a property or method beside its inputs; `kpis.py` and the routes read it. Start with the phone screens (to zero) and `keynotes.per_day`. Done when the ratchet file lists only lines marked `# not money`, and the four counted files have been read and classified.

## 12AE5 Owner: what "Kept" means · owner
A pick-list: Kept is Net flow everywhere and the flow chart's last band is named "Kept as cash" (recommended); or Kept means cash not invested, and the Report and the Overview sentence say "Saved". Then a registry row for the name and a test that a registry label is rendered only through `fig.<key>.label`, so a template cannot type a figure's name beside another value.
