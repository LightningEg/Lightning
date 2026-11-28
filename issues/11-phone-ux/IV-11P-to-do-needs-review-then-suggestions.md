---
title: Phone To do puts what needs review first and suggestions below, with the count unchanged
type: polish
look: visual
pillar: plan
size: S
model: sonnet
status: new
created: 2026-11-28
by: Claude
github: 780
---

## Report
[r40](../7-planning-import-and-search/r40-one-money-plan/report.md) F5 (owner pick, 2026-11-28: two groups, same count).
"8 things need you" puts an SMS to file and interest payments to match beside "Make it a bill" offers, a 5 EGP and a
22 EGP overspend and a top-up, all at one weight ([evidence](../7-planning-import-and-search/r40-one-money-plan/evidence/phone-todo.jpg)).

## Fix
`lightning/workflows/todo.py` gives each row a group: Needs review (bills, payday, catch-up, sort, checks, prices,
matching) and Suggestions (make it a bill, adjust a limit, top up, other offers). `phone/todo.html` shows Needs review,
then a Suggestions heading; Home's three rows come from Needs review first. The count stays every item (A09.2).
Done when: a test on Mohab's sample finds the SMS and matching rows under Needs review, the offers under Suggestions,
and the count unchanged. Arabic headings; Part C at 360 and 320 px.
