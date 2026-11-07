---
title: Nine small places where two neighbouring figures disagree or a figure reads wrong (Scenarios "None None", 87,768 against 87,368, "+14,000" still to pay)
type: bug
look: visual
severity: medium
pillar: understand
size: M
status: new
created: 2026-11-06
by: Claude
---

## Report

Audit r26 F5 ([report](r26-user-test-pc-and-phone/report.md)) lists each with its page: (a) Free cash "Cash you own 87,768" against Accounts' Cash & bank 87,368 (400 brokerage cash, unsaid); (b) Scenarios "Lowest scheduled cash 86,288.36" (cents) against Cash planning "Lowest point ahead 51,420"; (c) Scenarios "First shortfall None None" (`planning/scenarios.html:12`); (d) Financial health "4 of the 6 figures you set a limit for" when one has no limit; (e) "Bills due, loans apart 0" under "Due before payday 1,480"; (f) Accounts "Gam'eya still to pay +14,000" added to what you own; (g) Budget "Plan leaves to save 19,401" beside "Not yet given a job 13,997" with nothing linking them; (h) Overview's Investing rate does not say it is a share of what you kept; (i) Spending's "Against your usual month" repeats "Against 2026-09" with one month of history.

## Fix

One wording or figure change each, with a rendered-text test per page: (a) say "including 400 in your brokerage" or use the same figure; (b) whole EGP and a line saying what each lowest point counts, or one name each; (c) "No shortfall"; (d) count only figures with a limit; (e) rename or drop the row; (f) "Gam'eya, counted in what you owe" without a plus; (g) one leftover line that names both; (h) "of what you kept"; (i) hide the usual-month line until it differs from the single month before.
