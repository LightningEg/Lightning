# Audit 3: is the edit journal (multi-device sync) solid?

2026-10-21 · Claude · main `6e1c043` · encrypted dummy profiles, in-process carrier, no live Cloudflare.

The owner asked whether the new multi-device sync holds up. This covers the edit journal ([4A](../../issues/4-edit-journal-and-devices/4A-edit-journal.md)):
`lightning/sync/journal/`, the device runtime and `cloudflare/journal/worker.mjs`. The design was read against its guarantees G1–G8, the code was read
on the money path, and each suspected gap was run against real encrypted journals. Every finding was item 4C; all are fixed (see *Fixed* below), each with a test in `tests/test_journal_audit3.py`.

## Verdict

**The skeleton is solid. Conflict detection on the screens' path is not.** Receipts, ordering, signatures, the hash chain, durable outboxes and crash
recovery hold. All 371 journal and sync tests pass. But a stale edit from a second device can silently overwrite a payment's amount. Replay cannot
tell when a replica has drifted. **Not ready for real money** until 4C1–4C4 were fixed; they now are.

## Findings

| Step | Severity | What happens | Evidence |
|---|---|---|---|
| 4C1 | High | **A stale amount edit overwrites the newer one, with no review.** A command's precondition is the hash of the `transactions` row only. Amount, account and category live in `ledger_entries`, and `updated_at` is left out of the hash. The home changes −20 to −30. The PC, which saw −20, saves −40. It is accepted and the −30 is lost. This breaks G4, on the path every app screen uses. | `test_4c1_…` |
| 4C2 | High | **Replay cannot detect drift.** Home and replica both update `journal_fp` from the effect's rows. The replica never rehashes what it actually wrote, so the fingerprint check after each commit always passes. A replica changed outside replay keeps accepting commits; only a snapshot repair runs the full check (`fingerprint(full=True)`). §4 promises a check "at checkpoints and after catch-up". | `test_4c2_…` |
| 4C3 | Medium | **Two conflict models on one transaction.** The journal register keeps field groups in `journal_records`. Commands change the ledger without updating them. A later register edit, even to notes only, merges the stale groups and puts the old amount back (−99 becomes −10 again). | `test_4c3_…` |
| 4C4 | Medium | **One refused mailbox request stalls sync.** If the home refuses a request (frozen during a move, staging full, a storage error), `pump` marks it refused and sends no reply. The device resends the same bytes under the same ID. The home's `INSERT OR IGNORE` drops them. In the test, the edit was still pending after 30 rounds; it only clears once the device's payload changes. | `test_4c4_…` |
| 4C5 | Medium | **Bulk actions carry no precondition.** `delete_many`, `set_category` and `bulk_update` run without a base, so the last selection wins over a concurrent edit. The code comment says so, but it breaks G4. Shown by hand; no test yet. | Probe |
| 4C6 | Low | **The worker reads too much per call.** `receive` lists up to 8,192 full mail values to return 20. The alarm, every 5 minutes while devices are active, lists every mail value. A full mailbox (128 MiB) can go over the Worker's memory and the free plan's row reads. Found by reading, not run on Cloudflare. | Reading |

Also by reading, low: if recording a `home-error` review itself fails (`_review_token` → `matches`), the exception leaves `process` and blocks every
origin, not just the one with the bad proposal (`home.py`, `process`).

## Fixed (2026-10-21, owner asked)

- **4C1:** a command's precondition hashes the record and every row it owns (`ON DELETE CASCADE` children), so the stale −40 now waits for review.
- **4C2:** a replica reads each applied row back, and after every catch-up recomputes the whole copy (`store.verify`); drift asks for a snapshot.
- **4C3:** a command that changes a transaction removes it from the register's field groups; the register refuses to edit it ("changed on another screen").
- **4C4:** the home answers a request it cannot take with `refused`; the device retries with a fresh request.
- **4C5:** bulk commands carry one hash over the selected rows.
- **4C6:** the worker stores each wire apart and lists 64 small entries; each profile also gets a monthly allowance (see Architecture › encrypted profiles).
- The `home-error` review no longer stops other origins when its comparison fails.

## What holds

- **At most once (G2):** a receipt is checked by hash. A reused identity with different content is refused, inherited receipts included.
- **Order and review (G6):** strict per-origin order with a staging window. A review blocks only its own origin. The review lane is idempotent and checks a token.
- **Chain (G3, G7):** commits are signed and hash-chained, the predecessor is checked before apply, and the scope is generation-bound. A proposal is authenticated before it is parsed.
- **Durability (G1):** the outbox and counter commit in one FULL-sync transaction. A store whose counter disagrees with its outbox refuses to open. Crash tests cover every boundary.
- **Mailbox:** requests are signed, with nonce and clock checks. Delivery is acknowledged only after a durable local receipt. Generation changes are compare-and-swap. Retirement records are never expired. Quotas are per sender and control capacity is reserved.

## Not built yet (so not audited)

As 4A §10 says: J6d home automation, J6e upgrades and backups, receipt pruning, the J6f cutover, live free-plan deployment, Android Doze
evidence and review of the two-of-three owner credential. The journal covers 125 of 149 POST routes.
