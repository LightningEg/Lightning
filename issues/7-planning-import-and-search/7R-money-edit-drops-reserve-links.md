---
title: Changing an expense's amount silently unlinks it from its reserve
type: owner
pillar: plan
status: new
created: 2026-10-26
by: Claude
skills: number-audit
app_version: 1.4.2
commit: 705945c
repo: app
---

## Report

Found by [Audit 8](../../reports/2026-10-26-engine-audit/report.md) (B7). Link 200 of an expense to a reserve, then edit the expense to 190: trigger `tr_ledger_edit_clears_reserve_links` (migration 0018) deletes the link, the reserve's spent goes to 0 and reserved cash jumps from 100 to 300, with no message. Deliberate (a changed payment may no longer belong to the reserve), but silent.

## Fix

Owner decision: keep the link capped at the new amount, or keep removing it and say so on Save ("Unlinked from the Trip reserve; link it again if it still belongs there").

**Owner decision, 2026-11-02:** same rule as 7U (keep the link while the edit still fits; otherwise unlink and say so). Build 7R and 7U together.

2026-11-02, built for the register's edit: `ReserveService.carry_links` puts a link back when the edited expense still fits (shrunk to a lower amount) and the Save message says when one no longer does; `tests/test_reserve_matching.py`. **Left:** the same on the transaction details edit, and 7U (bill and income links) with the same rule.
