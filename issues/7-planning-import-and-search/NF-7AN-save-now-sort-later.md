---
title: Save now, sort later: an entry with only an amount waits in To sort
type: feature
pillar: capture
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r31](r31-logging-entries/report.md) F2 (owner chose it, 2026-11-09). Evidence: [amount only](r31-logging-entries/evidence/phone-amount-only.png).
At the till the person knows the amount and nothing else is worth typing. Save with only an amount is refused: a
category is required.

## Fix
Money out or in saves without a category as *To sort* (a system category, not budgeted). Home's To do and the PC's
Needs you show "3 to sort · 410"; the list sorts them with one tap each (payee suggestions and rules apply as they do
on import review). Budget and Spending show the unsorted amount as its own line, never inside a category, and Safe to
spend already counts it because the cash left. Money rule to state in Architecture: an unsorted outflow is spending
with no category. Tests: save without category, the To do count, budget totals before and after sorting, Mohab step.
