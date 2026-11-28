---
title: One month, one story - Home, Budget, Plan, Overview and the payday step name each figure once and agree
type: polish
look: technical
pillar: plan
size: M
model: opus
status: new
created: 2026-11-28
by: Claude
github: 779
---

## Report
[r40](r40-one-money-plan/report.md) F7, F9, F10, F11, F18 and step M1 of [r41](r41-the-next-big-thing/report.md) phase 1 (owner adopted, 2026-11-27).
On Mohab's sample, 27 Nov, one day shows seven "what is left" figures: Safe to spend 51,420 and "about 331 a day" (Home);
"You keep 61,744 until 1 Dec" and Going out 15,980 without everyday spending (phone Plan); Left for everyday 1,324 of
Planned 9,619 (phone Budget); Left in plan 1,324 of 25,599 planned (PC Overview); Lowest point ahead 51,420 "10,324
below today" (PC Cash planning). The payday step adds Cash available to assign 84,768 and Left unassigned 57,016 beside
Free cash 104,768 and Safe to spend 71,420 the day after payday.

## Fix
One monthly flow (money in, bills, everyday, savings and goals, no job yet) read the same way on each screen:
1. Phone Plan says "you keep" with Safe to spend, not Free cash, or names Free cash as Free cash.
2. Going out over 30 days includes the everyday budget, or is renamed for what it holds.
3. "Planned" names one total everywhere (bills and everyday, or everyday alone, with its own name).
4. Lowest point ahead shows only when it differs from Safe to spend.
5. The payday step states how Cash available to assign and Left unassigned relate to Free cash and Safe to spend in
   one line each, from `lightning/planning/funding.py` figures (no arithmetic in templates).
Done when: `tests/test_figures_agree.py` gains a Mohab-sample check that each figure above appears with one name and
one value across the screens, and the Glossary rows match. Mohab's year passes. Check A16 and Arabic.
