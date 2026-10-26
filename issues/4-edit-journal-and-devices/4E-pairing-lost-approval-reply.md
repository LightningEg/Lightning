---
title: Pairing cannot resume after the home admits a device but its password-proof reply is lost
type: bug
area: devices
status: ready
created: 2026-10-26
by: Codex
---

## Report
Medium severity, confirmed during backend review. If the home has already confirmed the matching number and the joining PC's password proof succeeds, losing that reply leaves the home with an approved member and the PC still at the password step. Retrying fails; ordinary status recovery is blocked locally. This also affects first-replica enrollment.

## Investigation
Reviewed main at 1b07257. Inject a TimeoutError after the home processes the proof but before the client receives the reply: membership contains the PC, its stage remains `password`, retry reports `Open pairing on the home first`, and finish reports `Compare the numbers and enter your password first`.

`lightning/sync/journal/pairing.py` commits membership and deletes pending pairing in `_admit`. `lightning/runtime/journal_pairing.py:134` and `lightning/runtime/journal_enrollment.py` advance the local stage only after the reply. The former's `finish` accepts only `waiting`; the latter's finish has the same stage gate. The authenticated result cache exists but proof retries do not consult it.

Validation: existing number-matching, matching-security and pairing suites passed (15 tests). A separate temporary fault-injection reproduction confirmed the inconsistent states above; passing those existing suites does not cover this failure.

## Fix
Make admission replies idempotent against the original request and signing identity, with current membership/revocation checks. Persist a resumable proof-attempt state before network I/O, without storing passwords, and allow authenticated status reconciliation after uncertain delivery. Cover dropped proof replies, home/client process exits, repeated completion, expiry and revocation for compatible replicas and first enrollment.
