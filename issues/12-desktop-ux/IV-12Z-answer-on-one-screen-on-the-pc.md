---
title: The answer on one screen, the rest on request - Spending, Cash planning and Investments run 3 to 4 screens and repeat lists
type: polish
pillar: feel
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

Audit r35 F6 and F7 ([report](../12-desktop-ux/r35-ux-against-users-questions/report.md), [page lengths](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/metrics.json)). Owner decision 2026-11-09: **the answer on one screen, the rest on request**. Sample year at 1366 × 768, in screens: Spending 4.1, Cash planning 4.0, Investments 3.4, Settings › Your data 3.2, Categories 2.8, Recurring 2.6.

- **Spending** stacks eight charts (treemap, sparklines, usual-month bars, ranges, the calendar, two flows, month by month). [screen](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/birdview_expenses.webp)
- **Cash planning** lists the late bills in Needs you and again, with the same Mark paid buttons, in "The next 30 days" directly under it; "Can I afford this?" is a card inside the Lead card (A16); Zakat day is a loose row between cards. [screen](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/plan.webp)
- **Investments** shows "What changed" as five rows of 0 EGP, and a card whose content is "Nothing moved in this period." (A09.2: one line or gone). Its Lead says Cost 325,088 while the table says 725,088 (the flat is counted in one and not the other) with nothing to say why. [screen](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/investments.webp)
- **Overview** ends with two collapsed headings and a third of a screen of nothing. [screen](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/overview.webp)

IV-3AM3 put each tab's answer above the fold; this item is about what follows it.

## Fix

Each tab keeps, open: the header, the Lead, Needs you, the KPI row and the one detail that answers the first follow-up. Every other block is a titled row that opens in place ("Day by day", "Cash flow", "Month by month") and remembers that it was opened. A section with nothing to tell is one line. No list appears twice on a page.

## Built

12Z1: `tests/test_page_skeleton.py` fails a tab taller than 2.5 screens at 1366 x 768 (Transactions and Categories excepted); Spending, Cash planning, Holdings and Your data are listed in its `ALLOWED` with their step.

Built 12Z2: Cash planning lists a late bill in Needs you only, "Can I afford this?" is its own card, Zakat day is a line of the forecast card (`tests/test_plan_says_each_thing_once.py`). Built 12Z3: Spending keeps Where did it go? open; Is this period unusual?, Day by day, Cash flow and Month by month are closed rows that remember being opened, and Spending is within 2.5 screens. Their one-line summaries are still to write. Where is my cash heading? and What is promised? are closed rows that remember being opened, so Cash planning is within 2.5 screens.

## How to work on this item

One PR per step. After each: `python -m pytest -q tests/test_brand_audit.py tests/test_mohab_year.py` and the step's test. Mohab reads some of these blocks: open them in his steps, never delete what he checks. Delete the step's heading in the same commit.

## 12Z5 Overview's tail · S · sonnet · #498
Built: a finished setup no longer shows its heading; a quiet Investments period is one line (12Z4, `tests/test_investment_explain.py`). Left: Your position still ends the page as a closed heading. Opening it by default takes Overview past 2.5 screens, so it moves beside the KPI row instead. Done when Overview on the sample year has no collapsed heading followed by empty space.
