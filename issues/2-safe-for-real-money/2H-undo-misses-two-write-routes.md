---
title: Undo misses two kinds of change (money held for someone, the old Settings page) and then reverses the action before them
type: bug
area: transactions
status: ready
created: 2026-10-21
by: Claude
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
Found by [Audit 4](../../reports/audit-4.md) §2. Severity: medium (Undo reverses the wrong action).

The undo middleware groups a POST into one user action only when its first path segment is on a hand-kept list
(`ui/web.py:411`):
- `POST /money-from-others` (`ui/routes/dashboard.py:594`) and `POST /birdview/settings` are not on the list.
- Six listed roots have no write route: `bank-imports`, `imports`, `loans`, `people`, `physical-items`, `views`.

Verified: after `POST /money-from-others` posted a transaction, the undo history still showed the earlier "Link reimbursement
receipt". Undo would have reversed that, not the new entry. The automatic payment matching that follows every grouped write was
skipped too.

## Fix
Treat every successful non-GET request as a user action, with labels as an optional map. Exclude only the undo route itself
(`/history`) and the demo/sample loaders. Test: a POST to every write route leaves its own undo group.
