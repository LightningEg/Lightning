---
title: Phone Money says net worth fell this month while its chart and the Report say it rose - the change is counted from the end of day 1
type: bug
look: technical
severity: medium
pillar: understand
size: S
model: sonnet
status: ready
created: 2026-11-09
by: Claude
skills: guideline-audit, bug-hunt
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r35 F1 ([report](../12-desktop-ux/r35-ux-against-users-questions/report.md), [phone texts](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/texts.json), [screen](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/money-english-chart.webp)). On the demo household on 2026-11-09 the phone's Money says "Net worth 198,821 · −10,438 since the start of the month." The chart under it rises to 198,821, and Money › Report › This month says "Change in what you own +31,895".

Cause: `lightning/ui/phone/screens/money.py` `build` (line 104) takes `c.position.at(day.replace(day=1)).net_worth` as the start. A position "at" a day is the end of that day, so the salary and the bills of day 1 are already in it and the month's change leaves them out.

Reproduce: `python issues/12-desktop-ux/r35-ux-against-users-questions/evidence/phone_capture.py OUT`, then read `/money` and `/money/report` in `OUT/texts.json`.

## Fix

Call the owner: `c.position.change_in_net_worth(first_of_month, day)` (registry figure Change in net worth: net worth at the end, less the day before the start, less opening balances in the period). The screen subtracts nothing itself. Audit r36 F2 ([report](r36-figures-one-owner/report.md)): on the demo household that function returns +36,395, the figure the PC's Overview shows, where the phone says −10,438. Check the other phone screens for the same pattern (`grep -rn "replace(day=1)" lightning/ui/phone`).

Test: on one profile with income on day 1, phone Money's change equals the PC Overview's change in net worth for the month (IT-12AE1 holds this comparison as a strict xfail until this is fixed). Then `python -m pytest tests/test_mohab_year.py tests/test_mohab_phone.py -q`.
