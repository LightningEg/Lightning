---
title: Phone Money says net worth fell 10,438 this month where the Overview says it rose 36,395
type: bug
look: visual
severity: high
pillar: understand
size: S
model: sonnet
status: ready
created: 2026-11-10
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: a4f696b
repo: app
---

## Report
[r34](r34-accounts-and-transactions/report.md) N1. Evidence: [phone Money](r34-accounts-and-transactions/evidence/phone-money.png). Same profile, same day: the PC Overview says
"Net worth 198,821 · +36,395 this month"; the phone's Money tab says "−10,438 since the start of the month."
`lightning/ui/phone/screens/money.py` `build` compares today with `position.at(day.replace(day=1))`, the position at
the end of day 1, after the salary (45,000) and the interest (1,833) that arrive on the 1st: 36,395 − 46,833 = −10,438.
Anyone paid on the 1st is told every month that their net worth fell.

## Fix
Compare with the last day of the previous month (the Overview's own basis, one shared helper), and word it "this
month" on both. Test: on the sample month Money and the Overview show the same change.
