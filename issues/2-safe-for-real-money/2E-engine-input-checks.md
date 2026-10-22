---
title: The engine accepts some bad input - dates before an account opened, crafted ids, rounding of plan amounts
type: bug
area: transactions
status: ready
created: 2026-10-20
by: Claude
skills: bug-hunt, number-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§1 Engine). The formulas hold; these are gaps in what the write paths refuse. Items 1–5 (split decimals, gold-account money, cash below zero, unknown owner, planner amount) are fixed and removed; the numbering below is unchanged. Severity: low for the rest.

6. Low: dates before an account opened are accepted (1900-01-01; one 10 EGP entry in July cut average spending from 24,049 to 16,036 and lifted the
   emergency fund from 0.8 to 1.2 months), though history before opening is allowed on purpose (`transactions/service.py:486`): decide the rule first.
   A plan amount of 350.555 is silently rounded and a reserve of 12.345 is accepted (not rechecked). Fixed: a crafted category direction and ids ≥ 2^63
   on a transaction (the bad investment bucket was already refused).
7. Low: shown parts don't add up by rounding: "If you sold today" 130,586 against parts summing to 130,585; "Where money in went" 46,834 against 46,833.
   Round the parts so they sum to the shown total (largest remainder).
8. Low (tech): every investment post voids and reposts the month-end revaluation entries; a fuzz run left 456 void VAL transactions. Reuse them when unchanged.

## Fix
One branch per group (6, 7–8), each with a test that posts the bad input and expects a refusal or matching totals.
