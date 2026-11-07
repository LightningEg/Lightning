---
title: The phone gives three different "a day" allowances (2,057, 278, 219) for the same 25 days
type: bug
look: visual
severity: high
pillar: plan
size: S
status: new
created: 2026-11-06
by: Claude
---

## Report

Audit r26 F1 ([report](r26-user-test-pc-and-phone/report.md)). On the sample on 2026-11-06, the phone's Home says "About 2,057 a day until payday on 2026-12-01" (Safe to spend 51,420 ÷ 25, money *on top of* the plan), the phone's Budget says "About 278 a day for 25 days" (Left in plan 6,948 ÷ 25, bills still to pay included) and the PC's Budget says "5,468 for everyday, about 219 a day". IV-3H CP-1 (done) chose one daily figure, on Budget, and "on top of your plan" for Safe to spend; the PC follows it, the phone does not. Reproduce: `python issues/12-desktop-ux/r26-user-test-pc-and-phone/evidence/probe.py` (lines F1).

## Fix

The phone Home line under Safe to spend says "on top of your plan until <payday>" with no per-day figure; the phone Budget uses the same everyday figure as the PC (left in plan less bills still to pay, ÷ days left), from one Python function both read. Test: on the sample, phone Home has no "a day", and phone and PC Budget show the same per-day figure; a Mohab step reads it on both.
