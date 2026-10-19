---
title: A planned payment due on a public holiday doesn't move to a working day
type: feature
area: planning
status: ready
created: 2026-10-19
by: Claude
github: 50
was: 7F1
---

## Report
`planning.schedule.on_working_day` moves Friday and Saturday only. A payment on a fixed public holiday (7 Jan, 25 Jan, 25 Apr, 1 May, 30 Jun, 23 Jul, 6 Oct) stays there, so the forecast is a day off.

## Fix
One named constant of the fixed-date holidays, treated like the weekend, moving until a working day; moon-set holidays (Eid, Sham El-Nessim) stay out, with a comment. Tests in `tests/test_planning.py`; keep `describe` true. Small and self-contained: GitHub #50.
