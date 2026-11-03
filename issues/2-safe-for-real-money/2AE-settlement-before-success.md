---
title: Save responses finish before required payment matching
type: bug
look: technical
severity: medium
pillar: protect
size: M
status: new
post: no
created: 2026-11-03
by: Codex
app_version: 1.5.4
commit: 89848dc0e4ce35bb18f72e861c7c620d8052fae4
repo: app
---

## Report

[Code audit F1](../../reports/2026-11-03-code-quality-and-smart-features/report.md) reproduces response completion before a failing settlement step in `lightning/ui/web.py:545–571`. Run the adjacent `evidence/reproduce.py`: the 303 and final body precede the injected storage error. This is isolated middleware evidence, not a real-disk loss reproduction.

## Fix

Define whether settlement is required or deferred. For required settlement, execute primary write and matching in one explicit workflow/transaction and send success only after commit. For deferred work, persist a retryable pending state and communicate it. Add full route fault injection, retry/idempotency, undo and journal-mode tests. Do not hide errors or move encrypted database use to another thread.

Not posted: affects financial consistency and requires workflow design review.

## Implementation · 2026-11-03

Matching moved into the response-start interception before success headers are forwarded. Targeted tests cover order, injected failure, rejected requests, read-only profiles and journal exclusion. Primary route writes still commit independently; retain this item for integrated fault/retry/undo tests and the required-versus-deferred workflow decision.

## Atomic entry workflows · 2026-11-03

Register entry/create/edit, investment entry, cash quick-add and transaction popups now use `workflows/save.settled_write`: the save, form retry marker and payment matching share an outer database transaction. UI scopes contain no awaits. After commit, the request marks matching complete so the response middleware does not repeat it. Journal commands keep their own settlement authority. Other write routes retain the response-boundary fallback; broader command-by-command coverage remains open.

Regression: `tests/test_atomic_entry_save.py` injects a failure after real settlement, verifies transaction/receipt/link rollback, retries the same token once, and checks one undo removes the payment link with the entry.
