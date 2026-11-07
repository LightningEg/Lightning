---
title: Budget says "over your plan's pace" every month for a person whose spending is always heavy in the first week
type: bug
look: visual
severity: medium
pillar: plan
size: M
status: new
created: 2026-11-06
by: Claude
---

## Report

Audit r26 F2 ([report](r26-user-test-pc-and-phone/report.md)). On day 6 the PC Budget headline says "You are 2,227 over your plan's pace" and Everyday spending says the same, while its own footer reads "−59 against 2026-10 by day 6", and October ended on plan (9,674 against 9,619). The plan's pace is a straight line from day 1; this person's month always starts with the big grocery shop (2nd) and the gym's 900 (4th), a monthly fixed payment not set up as recurring. The phone shows "Health 900 of 900 · Ahead of pace" for the same payment (r24 F5 fixed paid items only when they are recurring). A warning that fires every normal month stops being read. IV-3H BU-4 asks for a pace but does not cover the shape of the month.

## Fix

Pace against the person's usual cumulative curve by day (the last two or three completed months) when there is enough history, the straight line otherwise; and a category whose whole plan was paid in one payment equal to last month's says "Paid for this month", not "Ahead of pace". Never say "over pace" while spending is at or below the usual month by the same day. Tests: the sample on day 6 is not over pace; a month that really is heavier than usual is.
