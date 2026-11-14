---
title: Saving done this month is counted twice in Safe to spend
type: bug
look: technical
severity: high
pillar: plan
size: L
model: opus
status: new
created: 2026-11-14
by: Claude
github: 670
---

## Report
[r37](r37-cash-planning-workflow/report.md) W1, W2. Demo household, 2026-11-14. Safe to spend is 51,420 after an *Emergency fund top-up* of 5,404. Press *Refill 5,404* on Reserves: Safe to spend becomes 46,016 and the plan asks for 5,179 more this month. On `/payday` the page says "Safe to spend stays at 46,016 EGP"; after *Confirm cash assignments* it is 38,172 and a new proposal is offered at once. Reproduce: `evidence/flows/k.js`, then `m.js`.

Cause: `EmergencyFund.top_up` (`lightning/budgeting/domain.py:244`) is the gap ÷ 24 with no memory of what moved this month; `CashForecaster.forecast` takes it whole (`lightning/planning/forecast.py:302`). A goal's monthly need behaves the same.

W2: *Refill in instalments* (`forecast.py` `refill_schedule`) offers all of Safe to spend on the next income date, then rows at −51,420 and −78,273 under "keep Safe to spend at or above zero where they can": future rows are worked out on today's cash.

## Fix
## 7AV1 This month's moves count against this month's ask · M · opus
The month's *Emergency fund top-up* and *Saving for goals* are what the month asked for at its start less what was set aside since (never below zero). Done when: after *Refill* by the offered amount, and after *Confirm cash assignments*, Safe to spend is unchanged and the page offers nothing more this month; `tests/test_safe_to_spend_after_saving.py` proves both, and Mohab's year still passes. Owner approves the rule before it is built (money logic).

## 7AV2 The payday page tells the truth · S · sonnet
"Safe to spend stays at ..." is read from the forecast run with the proposal applied; parts add up to the plan's own figures (no 5,403 against 5,404). Done when: a test confirms the sentence equals Safe to spend after Confirm.

## 7AV3 Instalments that keep their promise · M · opus
Each instalment is at most the month's ask, or the rows count the income expected by their date; no row shows Safe to spend below zero while the sentence above says otherwise. Done when: a test over the demo household finds no negative row.
