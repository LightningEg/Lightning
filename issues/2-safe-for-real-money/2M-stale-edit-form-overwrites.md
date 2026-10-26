---
title: A stale transaction edit form can silently reverse a newer amount
type: bug
area: transactions
status: building
created: 2026-10-23
by: Codex
skills: bug-hunt, number-audit
app_version: 1.4.2
commit: a19c844
repo: app
---

## Report

Severity: high. [Audit 4](../../reports/2026-10-23-backend-correctness/report.md) owns the button sequence, observed result, source locations and scope for 2M. [Workflow probes](../../reports/2026-10-23-backend-correctness/evidence/workflow_probes.py) and [results](../../reports/2026-10-23-backend-correctness/evidence/workflow-results.txt) reproduce it on temporary dummy ledgers.

## Fix

Include a revision/hash in each financial edit form, check it atomically when saving and preserve stale inputs for conflict review. Test note-only stale saves after amount, account and owner changes; include inline edit and journal form timing in the fix review.

## Repair progress

Popup, phone popup, inline register and split forms now check a header-and-ledger revision inside the write transaction. Tests cover newer amount/account/owner changes, retained conflict inputs, valid fresh saves and a durable replica proposal. Legacy programmatic requests without a revision retain their prior contract. Ownership, conversion and investment route guards are ready; their three hidden template fields remain unapplied. The original hold was Claude’s 3W template claim, which ends when #76 is integrated. The reviewable patch is `reports/2026-10-23-backend-correctness/evidence/form-revision-fields.patch`; apply it and verify stale/fresh saves for all three workflows. Keep this item open until those forms emit the token and pass their workflow tests.
