---
title: Edit journal: a stale edit can overwrite money, and replay cannot see drift
type: bug
area: devices
status: ready
created: 2026-10-21
by: Claude
---

# Edit journal: Audit 3 fixes

Found in [Audit 3](../../reports/audit-3.md). Steps 4C1–4C4 are strict known gaps in `tests/test_journal_audit3.py`; remove a marker when its step
is fixed. Fix 4C1–4C4 before the J6 cutover ([4A](4A-edit-journal.md) §10). Files are in the journal claims in `NOW.md`.

## 4C1 A command's precondition covers its whole record

`commands.target_slot` → `adapter.row_token` hashes only the target row. A transaction's money is in `ledger_entries`, so a stale amount edit is
accepted. Make the base token the hash of the record and its child rows (a transaction with its lines; check every `target` in `areas/` the same way).
The saving device and `_consider_command` must compute the same token.

## 4C2 Replay checks the replica's real rows

`CashAdapter.apply` calls `remember(domain["rows"])`, so the cached fingerprint is built from the effect and always matches. Rehash the touched rows
read back from the replica's tables. Run `fingerprint(full=True)` after catch-up and at checkpoints (4A §4), and on a mismatch request a snapshot.

## 4C3 One conflict model per transaction

The register's field groups (`journal_records`) go stale when a command changes the same transaction, and a later register edit reverts it. Either
send register edits as commands, or build the current groups from the ledger at confirmation.

## 4C4 A refused mailbox request still gets an answer

In `MailboxPeer.pump`, a `JournalError` from `handle` marks the row refused and sends no reply. The retry has the same ID and is dropped. Reply with
the refusal (`reject`/`held`, as `_round` already does for `receive`), and treat transient errors (frozen, staging full, storage) as retryable.

## 4C5 Bulk actions carry a base per row

`transactions.delete_many`, `set_category` and `bulk_update` have no precondition. Send each selected row's token. When any row has changed, the
action waits for review.

## 4C6 The worker reads only what it returns

`receive` lists 8,192 full values, and `alarm` lists every mail value. Keep the wire under its own key (as snapshot chunks do) and list small pages of
keys; keep expiry in a sorted index. Measure against the free plan's row reads.

Also: if `_review_token` fails while recording a `home-error` review, the exception leaves `process` and blocks every origin. Catch it there.
