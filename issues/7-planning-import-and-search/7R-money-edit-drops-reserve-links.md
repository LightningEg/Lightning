---
title: Changing an expense's amount silently unlinks it from its reserve
type: owner
area: planning
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
