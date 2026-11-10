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

The start is the last day of the month before (`day.replace(day=1) - timedelta(days=1)`), the same month-end the chart draws. On the first of a month the sentence then covers that day's movement. Check Home and any other phone screen for the same pattern (`grep -rn "replace(day=1)" lightning/ui/phone`).

Test: in `tests/` beside the phone Money tests, a profile with income on day 1 and spending later: `since_start` equals net worth now less net worth at the last month's end, and has the same sign as the Report's net-worth change for This month. Then `python -m pytest tests/test_mohab_year.py -q`.
