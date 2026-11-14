---
title: Cash planning's breakdown rows lead to their pages, and the payday step is offered when the salary lands
type: polish
look: visual
pillar: plan
size: M
model: sonnet
status: new
created: 2026-11-14
by: Claude
github: 672
---

## Report
[r37](r37-cash-planning-workflow/report.md) L1, L2. On the PC the rows of *How safe to spend is worked out* (Budget until payday, Saving for goals, Emergency fund top-up, Rest of savings target) are plain text, and Reserves cannot be reached from Cash planning (the phone's Plan has a Reserves card). `/payday` is linked only from the weekly review's folded actions; it lights Budget in the sidebar while its button says Cash planning; nothing offers it when the salary is marked received.

## Fix
Each breakdown row links to the page that sets it (`/budget`, `/plan/reserves`, the savings target in Budget settings). `/payday` moves under the Plan tab in `lightning/ui/sections.py`, gets a link in Plan's menu, and the message after *Mark received* on an income offers "Fund your payday plan". Done when: `tests/test_budget_cash_page_pattern.py` finds the links and the lit tab, and a test marks the salary received and finds the offer. Check A16 and the phone (Part C).
