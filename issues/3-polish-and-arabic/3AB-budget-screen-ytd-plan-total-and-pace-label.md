---
title: Budget screen: the year-to-date plan total disagrees with its rows, and the pace chart labels overlap
type: bug
area: budget
status: new
created: 2026-10-21
by: Claude Sonnet 5.5
skills: site-recapture
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
Found recapturing the website's screens (sample on 2026-10-04, `LIGHTNING_TODAY=2026-10-04 python -m lightning --sample`).
- **Year to date (`/budget?period=ytd`):** the headline says "You spent 3,410 of the 68,850 planned" and the card says "Planned 68,850", while the plan exists only from 2026-10-01 and its rows add up to 38,428 (October's plan; Personal 32,928 + Loan payments 4,500 + Zakat 1,000). "Spending by group" shows Personal 36,640 and System Categories 32,210, which are not the rows' sums either. Left in plan reads 65,440; the monthly view says 35,018. Severity: medium (two plan totals for one plan).
- **This month (`/budget?month=2026-10`):** in "Is everyday spending on pace?" the label "Plan's pace 2,577" sits on the dashed plan line and the 3,410 marker (A16: overlapping labels). Severity: low.

The website therefore keeps its 2026-10-15 Budget screens (`budget.webp`, `b-budget.webp`, `a-budget.webp`) and their figures (38,034 planned, 3,410 spent, 34,624 left, 1,481 a day) on How It Works, Budget App Egypt and Net Worth, Budget and Expense Tracker, English and Arabic.

## Fix
Make the year-to-date plan total the sum of the months that have a plan, and move the pace label off the line. Then recapture the Budget screens, replace those figures with the app's (38,428 planned, 3,410 spent, 35,018 left, about 591 a day; 833 over the plan's pace) and say so in the website README › App screenshots.
