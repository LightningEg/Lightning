---
title: The engine accepts some bad input - dates before an account opened, crafted ids, rounding of plan amounts
type: bug
look: technical
severity: low
pillar: capture
size: M
status: ready
post: no
created: 2026-10-20
by: Claude
skills: bug-hunt, number-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§1 Engine). The formulas hold; these are gaps in what the write paths refuse. Items 1–5 (split decimals, gold-account money, cash below zero, unknown owner, planner amount) are fixed and removed; the numbering below is unchanged. Severity: low for the rest.

6. Low: dates before an account opened are accepted (1900-01-01; one 10 EGP entry in July cut average spending from 24,049 to 16,036 and lifted the
   emergency fund from 0.8 to 1.2 months), though history before opening is allowed on purpose (`transactions/service.py:486`): decide the rule first.
   Fixed: a crafted category direction, ids ≥ 2^63 on a transaction, and a plan or reserve amount with more decimals than its currency allows
   (the bad investment bucket was already refused).
   2026-10-29, [use-case audit](../../reports/2026-10-29-use-case-audit/report.md) F1: the cash guard checks only from the account's
   opening date (`_refuse_cash_below_zero`, `start = max(first, opening_date)`), so moving the opening date past existing spending,
   or spending before it, leaves a balance below zero (−9,000 on 2026-01-31) that Integrity then reports as an ISSUE. The rule to
   decide: either the guard covers days before opening too (`tests/test_transactions.py::test_restore_allows_transaction_before_account_opening_date`
   changes), or an opening date cannot move past the account's first transaction.
7. Low: shown parts don't add up by rounding: "If you sold today" 130,586 against parts summing to 130,585; "Where money in went" 46,834 against 46,833.
   Round the parts so they sum to the shown total (largest remainder).
8. Low (tech): every investment post voids and reposts the month-end revaluation entries; a fuzz run left 456 void VAL transactions. Reuse them when unchanged.

## Fix
One branch per group (6, 7–8), each with a test that posts the bad input and expects a refusal or matching totals.

**Not posted to contributors (2026-10-31):** its remaining rule (dates before an account opened) needs the owner's decision first.
