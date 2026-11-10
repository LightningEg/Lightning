---
title: Suggestions with sensible defaults and honest counts - Refill offers to empty Safe to spend, Needs you counts three ways, a year is compared with nothing
type: polish
pillar: plan
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: guideline-audit, bug-hunt
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r35 F9, F10 and F11 ([report](../12-desktop-ux/r35-ux-against-users-questions/report.md)). Owner direction 2026-11-09: Lightning notices and proposes the next step, and does repeated work, always as a suggestion the person confirms. The suggestions exist (NF-3AZ); these are the places where the first thing offered is not the thing a careful friend would offer.

- **Refill.** Reserves' filled button is "Refill 117,786", "After this, Safe to spend is 897 EGP" (PC, sample year) and "Refill 51,420", "Safe to spend is 0 EGP" (phone, demo). BT-2AH made that amount safe for the plan; it is still the whole of the figure the phone's Home leads with, offered first, ahead of "Refill in instalments". The page says "The aim is six" where Limits says "Below 3 months". [PC](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/plan_reserves.webp), [phone](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-plan-budget-health-reserves.webp)
- **Needs you on Overview** says 17 in its heading, "Bills and payments · 7" on its one row and "Show all 4" under it. [Overview](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/overview.webp)
- **Reports** says "This year against last year · +315,749 against 0 before" in rose, and shows the same 3,410 for This month and This quarter in a quarter's first month. [Reports](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/sheet-compare-reports-import-add.webp)
- **Late bills on the PC** are six rows with six Mark paid buttons; the phone has a catch-up flow for the same state (C11).

## Fix

The first offer is the modest one, a count is the number of rows the person will see, and a comparison with nothing says so. One PR per step.

## How to work on this item

Money logic stays in the services (`lightning/` services, never templates). After each step: its test and `python -m pytest -q tests/test_mohab_year.py tests/test_refill_preview.py tests/test_refill_schedule.py tests/test_needs_you_consequences.py`. Delete the step's heading in the same commit.

Built: 12AA1 (owner, 2026-11-10: monthly top-up first, aim six months; `ai/PROJECT_OVERVIEW.md`), 12AA2 (`tests/test_refill_offers_the_top_up_first.py`), 12AA3 (`tests/test_needs_you_one_count.py`, #494), 12AA4 (`tests/test_reports_compare_with_nothing.py`, #495).

## 12AA5 Catch up on late bills, on the PC · M · opus
Files: `lightning/ui/templates/planning/`, the planning routes; reuse the phone's catch-up service calls. With three or more late rows Cash planning offers one "Catch up": each late bill in turn, paid (on which day, from which account, a matching payment suggested first) or not yet, then a summary with Undo. Done when a test walks three late bills through it and the ledger and Due before payday move by exactly the paid ones.
