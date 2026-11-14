---
title: Three small cash planning fixes: Upcoming's month comparison, Recurring's sentence, paying a bill with no category
type: bug
look: visual
severity: medium
pillar: plan
size: M
model: sonnet
status: new
created: 2026-11-14
by: Claude
github: 673
---

## Report
[r37](r37-cash-planning-workflow/report.md) W4, W5, P1.

- Upcoming says "2,000 more than October" when both months are 17,980: this month's total counts gam'eya instalments, `_out_total` (`lightning/planning/calendar.py:126`) does not.
- Recurring leads "Your bills take 13,480 a month, 36% of your income": 13,480 is 30%; 36% belongs to 15,980, bills and loans.
- A bill added without a category (the field is optional) cannot be paid: "Give Old bill a category first", shown twice, with no field and no link; in Catch up this stops the flow.

## Fix
One total for a month, used for both sides of the comparison. The Recurring sentence takes its amount and its share from the same figure. The pay page shows a category field when the item has none and saves it with the payment; the message shows once. Done when: a test for each (equal months say "The same as"; the sentence's share equals amount ÷ income; a category-less bill is paid from Catch up in one step).
