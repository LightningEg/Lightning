---
title: Payday is the salary only: other income does not shorten Safe to spend's window
type: bug
look: technical
severity: medium
pillar: plan
size: M
model: opus
status: new
created: 2026-11-14
by: Claude
github: 674
---

## Report
[r37](r37-cash-planning-workflow/report.md) W6. Adding an 8,000 side income on the 25th turned "until payday 1 Dec" into "until 25 Nov" on Plan and Home; *Lowest point ahead* stopped matching Safe to spend. The Glossary says payday is the salary day; the forecast takes the next income of any kind (`lightning/planning/forecast.py`, `next_income`). On Upcoming, mid-month, the hero shows the payday already past ("Payday 1 Nov · Coming in 45,000").

Owner, 2026-11-14 (question dialog): payday is the salary only.

## Fix
The window ends on the next salary (the item set up as the salary; with none, the largest regular income); other income before it is money in inside the window. Upcoming's hero names the next payday from today. Glossary: Payday and Safe to spend say so. Done when: a test adds a small income before the salary and the window's end does not move while Safe to spend rises by that income; Mohab's year passes.
