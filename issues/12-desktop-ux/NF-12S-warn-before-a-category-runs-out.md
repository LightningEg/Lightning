---
title: Warn before a category runs out, with Move room or Raise
type: feature
pillar: plan
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
skills: bug-hunt, guideline-audit
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r32](r32-budget-and-cash-planning/report.md) F2 (owner chose it, 2026-11-09). A category's sheet already says "Ahead of pace: 70% spent, 30% of
the month gone", but only when opened. Nothing says so on Home or in Needs you until the limit is passed.

## Fix
When a flexible category's pace will pass its limit before the month ends (spent so far ÷ days gone × days in month >
limit, after day 5, and not a bill-only category), Home's To do and the PC's Needs you show one row: "Food &
Groceries will run out around the 21st" with *Move room* (the existing cover offer) and *Raise*. One row per
category, gone when it is back on pace or snoozed. Service-side only (`workflows/todo.py`); the phone's reminder
may carry it. Tests: on pace, ahead, bill-only, snoozed; Mohab step.
