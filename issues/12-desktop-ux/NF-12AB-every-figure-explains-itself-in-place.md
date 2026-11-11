---
title: Every headline figure explains itself in place - one gesture and one label instead of "Show the numbers", "How it is worked out", "See details", "See them" and bare chevrons
type: feature
pillar: understand
size: L
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: guideline-audit, bug-hunt
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r35 F12 ([report](../12-desktop-ux/r35-ux-against-users-questions/report.md)). Owner direction 2026-11-09: explain every figure in place. Today a figure's working is reached six ways: "Show the numbers" (Overview, charts), "How it is worked out" (the Safe to spend KPI, a link to another page), "See details" and "See them" (Needs you, in rose), "Opens Cash planning" (a KPI's foot) and a bare chevron (Limits, What you own). Some open in place, some leave the page; a person cannot predict which. [Overview](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/overview.webp), [Limits](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/financial-health.webp), [Cash planning](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/plan.webp)

The working itself exists: Cash planning's "How safe to spend is worked out" and Accounts' "How it adds up" are the model.

## Fix

A headline figure (a Lead, a KPI, a phone hero) is itself the control. Clicking or tapping it opens its working in place: the rows that add up to it, as Cash planning draws them, what changed it since the comparison, and one link, "Open <its home page>" (A09.2: one home per figure). One label for the text link where a link is needed. The rows come from the service that owns the figure; no arithmetic in templates or JavaScript.

Owner, 2026-11-10 (12AB1): on the PC the working opens under the figure in its card; on the phone in a sheet from the bottom; the one label is "How it adds up". Written into A08.1 (PC) and C06.1 (phone) in both repos (2026-11-11). 12AB2 built: `lightning/core/working.py` (Working, WorkingRow); Position.net_worth_working and portfolio_working, CashForecast.safe_to_spend_working, EverydayBudget.left_working, CashFlow.savings_rate_working, EmergencyFund.working; `tests/test_figure_working.py`. Next: 12AB3.

## How to work on this item

Steps in order. `python tools/guideline.py A08`, `A09`, `C06`. After each: `python -m pytest -q tests/test_brand_audit.py tests/test_mohab_year.py`. Delete the step's heading in the same commit.

## 12AB3 The PC's Leads and KPIs open their working in place · L · opus
One partial and one script behaviour; the six old labels go. Keyboard: Enter opens, Escape closes; the figure has a button role and a name. Done when the skeleton test (IV-12Y2) finds one label for a working on every tab and no KPI that both opens in place and links away from the same control.

## 12AB4 The phone's heroes open their working as a sheet · M · opus
Home's Safe to spend opens its working (r27 J2: today the link lands on Due before payday), Budget's Left in plan and Money's Net worth likewise. Done when a browser test taps each hero and finds the rows of 12AB2 and one link to the home page.
