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

## How to work on this item

Steps in order; one PR each. Read `lightning/ui/routes/` search route and its template only. After each: the step's test, `python -m pytest -q tests/test_mohab_year.py`, and `arabic-check` for new words. Delete the step's heading in the same commit.

## 7AQ1 The PC lists matching payments first, as the phone does · S · sonnet
One search service result for both devices: payments, then names and categories. Done when a test finds the same first five results for "food" on PC and phone templates.

## 7AQ2 A period grammar, tested alone · M · opus
A pure function: text to (subject words, period). English and Arabic: this month, last month, this year, last year, a year (2026), a month (2026-10, October, أكتوبر), "الشهر اللي فات". Unknown text returns no period. Done when a table-driven test covers each form and Arabic spellings (with IT-3BI1's normalisation if merged).

## 7AQ3 The answer card · M · opus
Subject resolved to a category, payee, account or tag (an exact or single clear match only; two candidates show both as choices). The card: total, comparison, count, rows, Open in Transactions. Done when a test on the sample year finds "food 2026-09" answering 5,044 (Spending's own figure for that month) and the link's filter returning the same rows.

## 7AQ4 Mohab asks three questions · S · sonnet
`tests/test_mohab_year.py`: Mohab types a category with a month, a payee with a year and a word that matches nothing, on PC and phone, and reads the card or the fallback.
