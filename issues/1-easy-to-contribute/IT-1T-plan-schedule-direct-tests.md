---
title: Direct tests for PlanSchedule and ScheduleSource
type: tech
pillar: build
size: S
model: sonnet
status: ready
created: 2026-11-05
by: Claude Sonnet 5.5
app_version: 1.5.4
repo: app
github: 341
---

## Report
`lightning/planning/schedule_view.py` defines `PlanSchedule` and `ScheduleSource`, which no test names (checked by name search in `tests/`); `reserve_goal_needs` has one test. Read the file first: if the classes turn out to be thin wrappers, say so on the GitHub issue and close it.

## Done when
A new test file builds a schedule from two sources and checks the order and the month split. It passes under `python -m pytest`.

Where to look: `lightning/planning/schedule_view.py` (66 lines).
Read first: the tests that call `reserve_goal_needs`.
