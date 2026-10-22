---
title: Phone overhaul, step 2 - quick add with the amount first, a transaction sheet with the plan left, swipe to sort, a health score
type: feature
area: phone
status: new
created: 2026-10-22
by: Claude Opus 5.5
skills: guideline-audit
app_version: 1.4.2
commit: c400e65
repo: app
---

## Report
The owner's design "Lightning on your phone" (2026-10-22) has fourteen fixes. 3AC built the frame and the six tabs
(guideline 3.34, Part C). Four points wait, and two were left out on purpose:

- **Quick add, amount first** (PDF sheet 1): Money in / Money out / Transfer on top, the amount with a number pad,
  then category chips (the usual categories first), one Primary "Add money out". Today Add asks which account, then
  opens the entry sheet with fields.
- **Transaction detail as a sheet** (PDF sheet 2): the arrow chip, name, date and account, the amount, then Category,
  Plan left ("1,100 of 8,000"), Note; Split and Done. Today a row opens the edit sheet; Plan left is new and must come
  from `BudgetService`, never the template.
- **Swipe left to set a category** (Transactions): reveal "Set category" on a row. Needs a gesture that does not fight
  C03.3 (swiping never changes tabs) and press-and-hold selection (C08.5).
- **Financial health as a score** ("78 of 100 · Steady", levers ranked by points gained): there is no 0-100 score in
  the app. A score is a financial rule: it needs the owner's definition first (Architecture › Financial rules).
- Left out: KPI cards that swipe sideways (C01: nothing scrolls sideways; hidden cards are missed), and money in
  shown in Azure (A03: Azure is money you hold; money in is green).

## Fix
Build the first two as phone sheets (C09), then ask the owner about the score and the swipe. Add each to Part C when it
is built, in both repos.
