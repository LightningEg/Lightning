---
title: Search answers a typed question - "food last month" gives the figure, its comparison and the rows, not a link to a filter
type: feature
pillar: capture
size: L
model: opus
status: new
created: 2026-11-09
by: Claude
skills: guideline-audit, bug-hunt
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r35 F13 ([report](../12-desktop-ux/r35-ux-against-users-questions/report.md)). Owner direction 2026-11-09: Lightning answers a typed question, offline, with no AI service. Today, on the PC, typing "food" in Search returns the category Food & Groceries and a link "Find transactions with food": two more clicks to see anything, and no total. The phone lists the matching payments at once (five rows), also without a total. [PC search](../12-desktop-ux/r35-ux-against-users-questions/evidence/pc/sheet-review-payday-account-search.webp), [phone texts](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/texts.json)

A person types what they want to know: "food last month", "Carrefour 2026", "rent", "how much on eating out".

## Fix

When the words name a category, a payee, an account or a tag, optionally with a period, the first result is an answer card: the total for the period (this month when none is typed), its comparison (the period before), the count, then the rows, largest first, and "Open in Transactions" carrying the same filter. The PC and the phone show the same card. Parsing is a small fixed grammar in Python (names matched with the existing `core.matching`, periods from a short list in English and Arabic); anything it does not understand falls back to today's results. The total comes from the reporting service, never from the rows on screen.

Status is `new`: the grammar's period words need the owner's eye in Arabic.

## Built

2026-11-10: 7AQ1 (the PC lists payments first through the phone's `phone_results`), 7AQ2 (`lightning/core/periods.py`, `tests/test_periods.py`) and 7AQ3 (`lightning/workflows/answers.py`,
`partials/search_answer.html` on PC and phone, `tests/test_search_answers.py`: "food 2026-09" answers 5,044, Spending's
own figure), 7AQ4 (Mohab asks three questions). 2026-11-11: 7AQ5 code: accounts ("CIB last month": its money out,
Spending's per-account figure) and tags ("#eid 2026"; the # makes it a tag) are answered too. The owner still checks the Arabic period
words (`_RELATIVE` and the month names in `core/periods.py`).

## How to work on this item

Steps in order; one PR each. Read `lightning/ui/routes/` search route and its template only. After each: the step's test, `python -m pytest -q tests/test_mohab_year.py`, and `arabic-check` for new words. Delete the step's heading in the same commit.

## 7AQ5 The owner's Arabic words · S · owner
The owner reads the Arabic period words in `core/periods.py` (`_RELATIVE`, the month names) and says which to add or
drop; then this item closes.
