---
title: One name, one figure across Budget, Cash planning and Home
type: polish
pillar: plan
size: M
model: opus
status: new
created: 2026-11-09
by: Claude
skills: bug-hunt, guideline-audit
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r32](r32-budget-and-cash-planning/report.md) N2-N5. The same words carry different numbers, or one headline sits on another idea's caption.
- **Left in plan** is 6,598 on the PC Budget and on Home, and 5,468 on the phone Budget (there it is the everyday part,
  which the PC calls "for everyday").
- **Home (phone):** "Safe to spend 51,420 EGP · About 249 a day until payday". 249 a day is the budget's everyday money
  (5,468 over 22 days); 51,420 over 22 days is about 2,337. A cash figure with a budget caption.
- **Lowest cash:** Cash planning says "Lowest point ahead 51,420"; Compare scenarios says "Lowest scheduled cash 86,288"
  for the same months (a note explains one counts everyday spending).
- **Unplanned income:** "Plan leaves to save 19,401" and, two rows below, "Not yet given a job 13,997".
- **The lead differs by device:** Cash planning leads with Safe to spend on the PC and with "Due before payday 1,130" on the phone.

## Fix
Phone Budget's hero is named "Left for everyday". **Owner, 2026-11-09:** Home leads with the everyday budget (what is
left for everyday, about 249 a day); Safe to spend stays the lead of Cash planning, with a link from Home. Scenarios
use the same lowest point as the plan. One row for unplanned income, the other a link. Record each name in
`ai/GLOSSARY.md`. Test: a figures test that reads each label on PC and phone and fails when one label has two values.
