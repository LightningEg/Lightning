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
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§1 Engine). The formulas hold; these are gaps in what the write paths refuse. Items 1–5 (split decimals, gold-account money, cash below zero, unknown owner, planner amount) and 7–8 (rounded parts add up: `tests/test_rounded_parts_add_up.py`; unchanged revaluation journals are reused: `tests/test_reevaluations.py::test_rebuilt_checkpoint_reuses_unchanged_revaluation_journals`) are fixed and removed; the numbering is unchanged. Severity: low for the rest.

6. Low: dates before an account opened are accepted (1900-01-01; one 10 EGP entry in July cut average spending from 24,049 to 16,036 and lifted the
   emergency fund from 0.8 to 1.2 months), though history before opening is allowed on purpose (`transactions/service.py:486`): decide the rule first.
   Fixed: a crafted category direction, ids ≥ 2^63 on a transaction, and a plan or reserve amount with more decimals than its currency allows
   (the bad investment bucket was already refused).
   2026-10-29, [use-case audit](../../reports/2026-10-29-use-case-audit/report.md) F1: the cash guard checks only from the account's
   opening date (`_refuse_cash_below_zero`, `start = max(first, opening_date)`), so moving the opening date past existing spending,
   or spending before it, leaves a balance below zero (−9,000 on 2026-01-31) that Integrity then reports as an ISSUE. The rule to
   decide: either the guard covers days before opening too (`tests/test_transactions.py::test_restore_allows_transaction_before_account_opening_date`
   changes), or an opening date cannot move past the account's first transaction.

## Fix
Item 6 is the only one left, with a test that posts the bad input and expects the ask.

**Owner decision, 2026-11-02 (item 6):** allow a date before the account opened, but ask once on save (like the far-from-market conversion rate: pressing Save again keeps it as typed). Build the ask in the register, popup and quick-add routes. 
