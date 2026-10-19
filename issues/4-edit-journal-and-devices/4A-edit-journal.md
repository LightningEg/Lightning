---
title: Edit journal: edit anywhere, one home confirms
type: feature
area: devices
status: building
created: 2026-10-16
by: unknown (moved from docs/proposals)
---

# Edit journal: edit anywhere, one home confirms

**Status: implementation authorized · 2026-10-16 · J1 core and experimental J2/J3 cash workflows built; stage acceptance remains open.** The owner requested this replacement after reviewing the moving-writer design and authorized all six delivery stages on 2026-10-16. Product decisions live in [Project Overview](../../docs/PROJECT_OVERVIEW.md#product-decisions-that-must-hold); the current implementation and experimental core live in [Architecture](../../docs/ARCHITECTURE.md#desktop-app-and-encrypted-profiles). This file owns the proposed protocol and its acceptance gates.

Every paired device saves edits immediately. One stable **home** validates them and publishes confirmed changes. Devices exchange those small changes continuously. Opening a PC does not borrow the ledger, move writing rights or require a whole database transfer. The home changes only through an explicit move or recovery.

## Contents

| Section | Read it when |
|---|---|
| 1. Product contract | Deciding what this delivers and what waits |
| 2. Guarantees and limits | Reviewing correctness or recovery claims |
| 3. Identity and messages | Building the wire format or journal |
| 4. Durable processing | Building save, confirmation, replay or snapshots |
| 5. Conflicts and duplicates | Building review and financial validation |
| 6. Small, continuous transfers | Building either network channel |
| 7. Authority, pairing and recovery | Building trust, revocation or moving home |
| 8. Compatibility and automatic work | Adding an entry kind or changing schema |
| 9. Retention and backups | Deleting history or restoring a device |
| 10. Delivery stages | Planning implementation |
| 11. Acceptance | Proving a stage can ship |

## 1. Product contract

- **Edit on any device, online or offline.** A successful save first persists an edit locally. A PC never needs writing rights. The home uses the same save path, then confirms locally when possible.
- **One stable home decides.** The phone is the default. Only the home applies proposals through the financial services and creates authoritative decisions. Other devices hold confirmed replicas and local pending edits.
- **Pending is useful and honest.** The register shows local pending additions, edits and deletes immediately, with the confirmed value still inspectable. Reports, balances and budget actuals use only confirmed data. An unavailable home delays confirmation, not capture. There is no claim that an offline edit is already in every device's ledger.
- **No routine handover.** No borrow, hand-back or Take back in this protocol. A deliberately chosen PC can be home; it confirms only while its profile is open. No background profile key is stored on a PC.
- **Review on the home.** Conflicts and possible duplicate payments wait there. On the originating device their state and reason remain visible. A refusal stays in *Not taken* for one week after the device first displays it, with *Add again* creating a new edit.
- **Trust once.** Existing owner choices remain: code, matching check digits and profile password during pairing; no later phone tap to sync; the phone can keep its data key wrapped by Android Keystore for background work. Locked screens still need the profile password.
- **Local or internet transport.** Use the existing pinned local link when available and the chosen Cloudflare mailbox otherwise. Neither transport calculates money. Firebase push is a wake-up hint, not a delivery or latency guarantee.
- **Home replacement remains exceptional.** Any paired device may become home with two of the three owner secrets. Section 7 distinguishes a complete move from recovery using an incomplete surviving copy.

This replaces the earlier automatic transfer of writing rights. It preserves local-first storage, Python financial rules, encrypted transport, home-only review, short visible history and the home's compatibility policy. It does not turn sync into a backup service.

**Why this design.** Copy-and-handover spends bandwidth on unchanged data and complicates everyday editing. Unrestricted merging of database rows cannot by itself enforce bill settlement, linked transfers or investment rules. This proposal keeps one financial decision point but removes it from the local save interaction. See the existing [competition analysis](../../docs/COMPETITION.md#actual-budget-code-analysis) for workflow lessons; no external sync engine is selected here.

## 2. Guarantees and limits

| ID | Contract |
|---|---|
| G1 | **Durable save.** Before saying saved, the device has persisted the edit and its identity. Process restarts, retries and replica replacement do not discard it. |
| G2 | **At most once per authority history.** An identical retry returns the recorded decision. Reusing an identity with different content is a protocol error. Compact duplicate-prevention records outlive visible history. |
| G3 | **One confirmed result.** Devices with the same authority generation and revision have the same canonical ledger fingerprint. They apply the home's exact results, not their own reinterpretation of the request. |
| G4 | **No silent conflicting overwrite.** Field-group preconditions and causal dependencies govern merging. Clocks never select a winning financial value. |
| G5 | **Financial invariants.** Confirmation runs the normal Python services in one transaction; ledger effects and the decision commit together. |
| G6 | **Causal order.** Each origin's financial edits reach a terminal decision in sequence; dependencies on earlier pending edits are explicit. A conflict cannot deadlock its own resolution. |
| G7 | **Authenticated authority.** Only currently trusted origins submit new work; only the authorized home signs confirmed results. Membership and authority generations are checked on both channels. |
| G8 | **Bounded visible history.** Detailed accepted history remains at least 30 days and until acknowledged by all currently paired devices. Receipt metadata and delete markers are separate, longer-lived correctness records. |

These hold for supported versions, honest clients, durable storage honoring successful flushes, and eventual communication. They do not promise survival of destroyed storage, recovery of an edit that existed only on a lost device, or instantaneous revocation of an offline device. OS power-loss durability still needs the evidence described in Architecture.

**Acceptance is scoped to a home generation.** Normal disconnection never changes that generation. Explicit lost-home recovery may start from an older verified checkpoint; the owner must see that cutoff. Edits on a retired branch are recovered as proposals, not silently treated as confirmed in the new branch. This exception is visible, tested and never triggered automatically by a timeout.

## 3. Identity and messages

Use a new protocol version; v1 and its fixture stay frozen. All encodings are canonical, versioned and bounded; unknown fields and duplicate JSON keys are refused. Domain records gain stable UUIDs. Local integer keys remain implementation details and never identify a record on the wire.

**Origin identity:** `(profile_id, device_id, incarnation_id, seq)`. Each installation has a random incarnation and a durable increasing sequence, allocated in the same transaction as its local edit. A new installation or an uncertain/restored counter gets a new incarnation approved by the home. Old queued edits retain their original identities. Installing a backup never reuses a sequence for new content.

| Message | Required content |
|---|---|
| Proposal | Origin identity; canonical payload hash; entry kind and version; resolved values; created UUIDs; changed field groups and their base tokens; explicit dependency IDs; last confirmed cursor; display time and zone; origin signature. |
| Decision | Proposal identity and hash; accepted, rejected or accepted-as-existing; bounded reason code; resolved UUID aliases; home generation and revision; exact effects when accepted. Waiting for review is a durable nonterminal status, not a rejection. |
| Confirmed batch | Contiguous decision revisions; previous batch/commit hash; home signature; deterministic domain effects and resulting record/group tokens. Rejections advance the decision revision with no financial effect. |
| Snapshot | A verified encrypted database plus a signed manifest binding profile, generation, revision, schema, canonical fingerprint, file hash, size and chunk hashes. |
| Acknowledgement | Specific envelope IDs durably received, and separately the highest contiguous confirmed cursor durably applied. Neither means the user has seen a decision. |

A cursor is `(generation, revision, commit_hash)`, never a bare number. A UUID alone does not establish causality or prevent replay. The signature binds the entire proposal; its payload is immutable once saved. Correcting it means another edit, not altering a queued one.

**Resolved effects:** the home records domain rows with UUID references, references assigned for display, exact decimal/date values, deletions, aliases and field-group tokens. The replica validates the typed effect schema, authority, predecessor and constraints, then applies the complete effect transaction through a dedicated Python replication service. It does not execute transmitted SQL, rerun categorisation, regenerate identifiers, settle bills or fetch prices.

The canonical fingerprint covers synchronized domain state using UUID references and normalized values. It excludes physical row IDs, SQLite sequences, device-local timestamps, outboxes and caches. This needs an explicit new fingerprint contract; the current whole-copy fingerprint must not be assumed suitable for independent replay.

## 4. Durable processing

### On every device

1. Validate the form against the available view. Resolve user choices, including date, selected category and decimal amounts; capture preconditions and dependencies.
2. Persist the signed proposal and advance the origin counter in a device-local encrypted outbox with FULL synchronous writes. Only then say *Saved on this device · Pending*.
3. Render a disposable overlay above the confirmed replica. Its failure cannot erase the proposal or contaminate reports. A pending delete appears as awaiting deletion rather than silently removing the confirmed evidence.
4. Deliver/retry from the outbox. Delivery to the mailbox is not confirmation. Retain payloads until their terminal decisions are durably stored and displayed locally; accepted edits are not removed from the overlay until the corresponding confirmed effects have arrived.
5. Apply complete confirmed commits in one replica transaction, advancing the cursor in that transaction. Rebuild the overlay from remaining proposals. A now-invalid overlay becomes *Needs review*; it is never dropped or silently rewritten.

### On the home

The canonical ledger, durable inbox, decision receipts, origin progress, record tokens, delete markers and confirmed effects live in **one encrypted database**. This removes the former cross-file atomicity ambiguity. The home may also have its own separate outbox; a crash between outbox save and confirmation is harmless because retry uses the same identity.

1. Authenticate the envelope and current membership before decrypting its financial payload. Check bounds, supported versions and signature. Do not parse or act on an unauthorized payload.
2. If the proposal already has a receipt, require the same hash and return its status. A future sequence is staged within a bounded gap window and missing IDs are requested. No clock-based reordering.
3. Persist the inbox item. For the next eligible proposal, resolve aliases, dependencies and group preconditions. Persist any review state; other origins continue while this origin waits.
4. In a single ledger transaction, run the financial services, capture every effect, assign group tokens and a revision, and store the terminal receipt and origin progress. A financial refusal rolls back all financial effects; recording the rejection and advancing progress then occurs atomically in a separate transaction.
5. Publish only committed results. A crash after commit but before response returns the stored result on retry. A response cannot claim success before the commit. Network operations and push calls never run inside the financial transaction.

Home signatures are produced from durable committed content; sending can be retried after a crash. The outbound stream is reconstructed from the ledger, not a second file that must commit atomically with it.

### Replay and resynchronization

Require the next cursor and exact predecessor hash before applying a batch. Duplicate commits are harmless; missing or inconsistent predecessors stop replay. Verify the canonical fingerprint at checkpoints and after catch-up. On a mismatch, preserve evidence and request a verified snapshot; never upload the mismatching replica as authority.

Stage and verify snapshots with the existing promotion foundation. Preserve local outboxes and unseen decisions independently of replica replacement. A snapshot contains receipt summaries, aliases, delete markers and compatibility metadata, but no other device's local outbox. After promotion, query the status of pending IDs and rebuild the overlay. A restored snapshot must not roll back authority-generation memory or origin counters.

## 5. Conflicts and duplicates

Each kind declares the groups of fields that must change together and its service-level preconditions. Amount, currency and postings of a financial transaction form one group; note or category may be separate when the service contract permits. A transfer and all its legs, or a split and its lines, are one atomic action. A version on each database row alone is insufficient.

Base tokens name the last confirmed change to a field group. For a record created or changed by an earlier pending edit, a proposal instead names that dependency's identity and expected result; the home resolves it from the receipt. Deletion markers and aliases prevent stale devices recreating removed identities.

| Situation | Result |
|---|---|
| Groups read/changed by the action still match | Validate and accept. |
| Only independent groups changed elsewhere | Apply only the requested groups, then validate the whole result. |
| Same group changed, including changed and changed back | Hold for review with base, current and proposed values. No automatic timestamp winner. |
| Target was deleted | Reject with deletion context; *Add again* needs a fresh UUID and current validation. |
| Delete would remove a record changed since its base | Review; keep is the safe initial choice. |
| Earlier dependency rejected | Reject dependent edits with that reason; advance sequence for each terminal outcome. |
| Same canonical category/account name added twice | If domain rules establish equivalence, return the existing UUID and persist an alias from the proposed UUID. Otherwise review. All dependent references resolve through that alias. |
| Proven same imported item | Use a namespaced source ID and validated equivalence to return the existing payment; never count it twice. |
| SMS and CSV merely resemble the same payment | Hold the incoming payment for review before posting. Keep the existing confirmed payment; offer link to it or post separately. Similarity alone neither merges nor double-counts money. |
| A bill occurrence is already linked to a payment | Do not partially accept a combined post-and-link action. Review the possible duplicate or reject the complete action; an explicit later choice may post an unrelated payment. |

**Review cannot block itself.** Home review commands use a separate idempotent control lane, not the blocked origin's financial sequence. They reference the waiting proposal and the exact review-state version. One transaction rechecks current preconditions, records the choice, resolves that proposal and unblocks its origin. A stale choice returns refreshed review; it cannot overwrite a later edit. No financial operation bypasses the normal services through this lane.

Unrelated origins continue during review. Later financial edits from a blocked origin stay visibly queued; the UI names the blocker. The first version favors strict per-origin order over a more complex dependency scheduler. Owner cancellation is a recorded terminal rejection, never deletion of a sequence slot.

Undo is a fresh, validated proposal referring to a retained accepted action. It can itself conflict; it is not restoration of old database rows without checks.

## 6. Small, continuous transfers

Both transports carry the same authenticated envelopes. A sync round exchanges capabilities, authority information and cursors; uploads missing proposals; downloads decisions and confirmed changes; and acknowledges durable progress. Devices request missing ranges instead of repeatedly sending everything. New edits trigger a short coalescing window; reconnect and app-open trigger catch-up. No tight polling loop.

- **Local link (default, owner 2026-10-16):** discover and try the already paired home on the local network, verify its saved TLS identity, then exchange deltas. This works without the mailbox. Availability of the authenticated link determines reachability; a shared network name alone is not proof. Authority freshness has the recovery limitation in section 7.
- **Internet fallback:** a Workers Free endpoint and one SQLite-backed Durable Object per profile hold opaque envelopes for paired recipients. An active foreground app uses a hibernating WebSocket; disconnected devices resume from durable cursors. Push contains only a mailbox wake-up hint. Routine authentication uses saved keys automatically; pairing codes/password proofs and matching digits are not repeated for sync.
- **Delivery:** delete a mailbox envelope only after a recipient durably acknowledges it, not after download starts. Lost acknowledgements cause retries. A sender retains its own durable source until the protocol permits pruning, so mailbox expiry is recoverable.
- **Snapshot fallback:** first pairing, history pruned before a device's cursor, verified divergence, or catch-up whose measured cost exceeds a snapshot. Use resumable, hashed chunks in the same SQLite Durable Object or through the local link. A few new expenses must never require the whole file.

**Initial resource limits, to measure in the prototype:** normal envelopes at most 64 KiB including framing; at most 50 proposals and 48 KiB encoded plaintext per normal batch; per-kind payload limits; bounded staging and gap buffers. Oversized imports are reviewed and divided into explicit per-payment actions before saving, with one import ID for progress and undo. Never silently split a transaction or transfer. Larger indivisible effects use a hashed, bounded chunk manifest and are applied only after complete verified assembly. Start with a 1 MiB maximum assembled effect and 200 MiB snapshot; refuse larger actions before acceptance with a clear reason, then revise limits only with evidence. Do not use decompression without strict expanded-size limits.

**Android availability.** FCM normal messages can be delayed in Doze, and repeated high-priority messages without visible notifications can be deprioritized. Periodic background work's 15-minute minimum is not a maximum delay. Catch up on foreground/resume, use supported bounded background work, and show the last confirmed sync and pending count. Never promise *within seconds* or invent a resume time for an unknown outage. Sources: [Firebase priority](https://firebase.google.com/docs/cloud-messaging/android-message-priority), [Android work scheduling](https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work).

**Cost and abuse.** Owner decision 2026-10-16: use Workers Free and SQLite-backed Durable Objects only; no R2, paid subscriptions or automatic upgrade. Development does not require live cloud credentials. A dedicated account and private domain remain the deployment target. Enforce authenticated mailbox creation, unguessable IDs, per-device request and byte limits, per-recipient queue quotas, upload quotas, bounded signatures before costly work, backoff and monitoring. A device exhausting its application quota must not consume another device's reserved control/recovery capacity. Measure request, duration, row read/write and storage usage against all free allowances, including push calls; a daily request count alone is not capacity evidence. [Durable Objects pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/) documents that operations exceeding Free limits fail. Provider quota exhaustion may stop the whole cloud route; pending edits remain on devices and the local link is still attempted.

Before deployment, verify actual edge-rule availability and whether blocked requests consume the Free allowances. Use fail-closed endpoints and check the account's subscription inventory; missing permission, unknown plans or paid/metered subscriptions block deployment. Budget alerts are informational, not a spending cap. A valid-shaped flood may still exhaust free capacity; there is no availability guarantee during abuse. Initially retain unacknowledged envelopes up to 30 days and temporary snapshots up to 7 days, with retries from devices after expiry. Authority retirement records must survive mailbox queue expiry. Owner setup is tracked as GitHub issues.

## 7. Authority, pairing and recovery

### Normal authority and trust

A profile has one home public key, an authority generation, a membership version and an approved device/incarnation set. These are distinct from the ledger schema and decision revision. All proposals, decisions and snapshot manifests bind the profile and generation. The home serializes confirmations; peers cannot turn their local overlays into confirmed data. Network timeout, app-open and phone sleep never elect a home.

Owner decision 2026-10-16: the Devices screen discovers nearby device names while pairing is explicitly open; the user never types an IP address or port. Pairing requires the six-digit code shown on the home, profile password proof, matching check digits on both screens and confirmation on the existing home. Discovery alone never admits a device. The proof is bound to the pairing transcript and both device keys; possession of a code alone is insufficient. A new device receives the verified authority and membership state with its snapshot. Repeated pairing does not reset another origin's sequence.

Use a fresh random group transport secret independent of the shared profile data key; derive domain-separated transport keys from it and bind an explicit key epoch. A revoked device must not derive the next secret from its old data key. Use authenticated encryption plus an outer device signature over the ciphertext and routing header, bound to recipient, profile, message type and envelope identity. Authenticate that outer signature before decrypting; the enclosed proposal retains its original signature across forwarding. Retransmit identical sealed bytes or use a fresh unique nonce; never reuse a nonce for different plaintext. TLS pinning remains an additional local-channel defense. Keys and plaintext financial payloads never enter logs or the plain control store.

On revocation, the home stops new work from that origin, advances membership, and rotates the transport key for remaining devices over their authenticated individual key channels. Deleting a certificate from the mailbox alone does not revoke a shared encryption key. Old data already held by a device cannot be erased remotely. Offline devices learn revocation on contact; no instantaneous remote-erasure promise. Old receipts remain valid historical evidence; a revoked device's unsent edits are not silently admitted as new work.

### Deliberately moving a reachable home

Use the existing two-of-three owner-secret rule, then a durable freeze-transfer-activate handshake. Freeze the old home before taking its final snapshot; drain its accepted work and include the inbox, receipts and protocol state. The target verifies everything before activation. The old home persists retirement before the new home confirms anything; an interrupted handover resumes idempotently and never infers success from timeout. Local pending outboxes remain on their origin devices and send to the successor.

A mailbox-backed profile also publishes the transition in the authority registry below. A local-only profile may move through this cooperative handshake; lost-home recovery of the same profile requires the registry, or an explicit new profile with re-pairing. No silent competing home.

### Lost-home recovery and stale devices

The internet mailbox has a **small authority registry**, separate from expiring message queues. It stores no financial plaintext: only profile identity, the current home/generation, owner-authority public key, transition certificates and recovery cutoff hashes. Generation changes use atomic compare-and-swap against the previous generation. Competing recovery attempts cannot both become the successor. A queued reply from an old attempt cannot undo a newer transition.

Recovery needs an online registry and owner authorization, a verified surviving snapshot, and an explicit display of its last confirmed revision/time and possible missing work. The successor preserves that prefix, starts a new generation and does not import the old home's unverified replacement database. The registry refuses further publication by the retired home. It is trusted to serialize authority transitions and preserve the latest record, although it cannot decrypt finance data. This control-plane trust is additional to the untrusted envelope carrier; pinned generation memory detects rollback on existing devices, and registry loss requires explicit repair rather than treating an empty registry as a new profile. If the registry is unavailable, devices keep local capture; they cannot force a same-profile home replacement.

**Two secrets must authorize recovery, not just unlock a screen.** Existing `keys.json` has a password lock and a recovery-key-plus-answer lock; the recovery key alone does not open the profile. Keep that scheme. Add an independent owner-authority signing credential protected by a reviewed two-of-three secret-sharing/key-wrapping construction; it must not be derivable from the profile data key or an ordinary paired-device key. The registry verifies its nonce-bound transition signature. Enrollment, every pair of secrets, wrong-secret throttling, credential changes, lost wrappers and revocation of obsolete recovery authority are mandatory security gates before recovery ships. Do not invent cryptographic primitives or treat a client boolean saying “two secrets checked” as proof. Ordinary sync never needs this credential.

**A registry cannot stop an offline old home from running.** A device retains its highest authenticated generation in durable control state, refuses older-generation confirmed streams once a successor is known, and exchanges this state on both channels. After a restart, restore or reconnect, check the registry when reachable before publishing new work. While it is unreachable, a known home may still confirm in its existing generation over the local link; those views can become a retired branch if recovery occurred elsewhere. Show last authority contact when stale. This is the explicit price of local operation during an outage; claiming immediate global fencing would instead require online authorization for every confirmation.

On seeing retirement, the old home stops confirming and preserves its branch. Original proposals after the recovery cutoff, including its own edits and those of other devices, are offered to the successor with their original signatures and causal chains. The successor's inherited receipt set prevents replay of the retained prefix. Branch-specific outcomes are kept as evidence; missing proposals are revalidated and may now conflict or be refused. Revoked origins require an explicit owner-reviewed import into fresh proposals. Devices preserve a comparison copy until review completes. They never silently overwrite either branch or report previously confirmed but now absent work as still confirmed.

If the only copy of some edit was on the lost device, it cannot be recovered. Show the limit before recovery, and offer a newer verified surviving checkpoint when one is available. Sync receipt retention cannot recover destroyed payloads.

## 8. Compatibility and automatic work

The home's app version defines the supported protocol, entry kinds, effect schemas and ledger schema. Publish a compatibility table with each release. Exchange capabilities before submitting work; distinguish “update this device” from “update the home.” Unsupported proposals stay pending without consuming their sequence; dependent work waits visibly. Never turn incompatibility into a financial rejection or discard a queue during upgrade.

Only the home migrates canonical schema, behind a durable migration barrier. Freeze confirmation, checkpoint, back up, migrate, publish the new capabilities and a snapshot, then resume. Capable replicas upgrade and take that snapshot; older ones continue viewing their last supported copy and retain pending work. Entry adapters preserve original signed payloads and record normalized interpretations. A kind that cannot be safely adapted goes to review; no silent semantic rewrite. A migration cannot bypass a waiting recovery transition.

**Capture may run anywhere; financial automation runs on the home.** Phone SMS capture/parsing creates local candidates or proposals even while the home is a PC. Bank CSV review on a PC behaves similarly. Receipt of an SMS is not authority to post it. Rules that choose values in the user's preview are captured in the proposal; the home checks current invariants without silently changing those confirmed choices.

Price fills, bill matching, ownership repairs and other automatic financial writes run only on the home and produce deterministic journal effects with stable job/source identities. Replica reads, overlay rebuilding and replay never run them. Audit all current save paths and hidden writes before enabling an area. Home writes in an unsupported area cannot bypass the journal and still claim incremental convergence: disable that area in the experimental profile until journal coverage exists.

## 9. Retention and backups

| Record | Retention and purpose |
|---|---|
| Local undecided proposal | Until a terminal decision is durably stored and displayed; no age-based deletion. Storage exhaustion stops a save before success is shown. |
| Detailed accepted history and before-values | At least 30 days and until all currently paired replicas have durably acknowledged it. An absent device can delay pruning; prompt for deliberate revocation, never silently remove it. |
| Rejected payload on its origin | One week after first display. Before display, retain it even if the device was offline for months. |
| Compact receipt | Keep proposal identity/hash, outcome code, generation/revision, dependency result tokens and required aliases for the lifetime of that authority history, including after payload pruning. Old retries return the same outcome; narrative details may be expired. |
| Delete markers, field-group tokens and UUID aliases | Keep while stale references or retries can arrive; the first implementation keeps compact records for the profile lifetime. They contain no deleted financial payload. |
| Retired generations and device incarnations | Durable rejection/redirect records, not subject to mailbox queue cleanup or visible-history pruning. |

Receipts are scoped to their authority history: inherited-prefix outcomes survive recovery, while proposals outside that prefix can get new decisions in the successor history. Preserve the relationship; never confuse an old-branch acceptance with a new-branch acceptance.

Profile backups must include confirmed ledger/protocol state, this device's encrypted outbox and identity manifest, plus the applicable key material. Use the profile/session lock to make a consistent package and record which other devices have acknowledged the checkpoint. Restore first preserves current queues, then imports backup proposals by original identity; it never rewinds a live origin counter. A stale replica takes a fresh snapshot. Restoring the home to an older ledger is an explicit recovery transition, not ordinary resume. Missing authority metadata blocks confirmation and requests repair.

Compaction tests must cover a returned device after more than 30 days, removed devices, delayed rejection delivery and a restored old backup. “Keep history for 30 days” does not authorize erasing the metadata needed to prevent duplicate money.

## 10. Delivery stages

No production protocol switch before complete write coverage. Early stages use isolated dummy profiles; they are end-to-end engineering milestones, not claims that the full product is ready. Claims belong in [NOW.md](../../NOW.md). The owner authorized J1–J6; stages proceed in order without treating a prototype as production acceptance.

**Current boundary:** J1–J3 cash workflows and experimental J4/J5 delivery/trust primitives are implemented; see Architecture for executable details and evidence. Development uses encrypted dummy profiles, a local Cloudflare runtime and injected carriers. Live free-plan deployment, Android push/scheduling and native/Arabic acceptance, complete fault/security evidence, native transition/enrollment UI, receipt pruning and full financial write coverage remain open. Interrupted-transition resumption, paged authority-chain verification and verified first-replica enrollment services now have fault/restart tests. J6 product integration/cutover is unbuilt. Other financial areas and automation stay disabled in journal profiles; the laboratory wire format is provisional. The owner authorized merging after completion, not bypassing these gates.

| Stage | Deliverable and exit gate |
|---|---|
| J1 — Local core | Exact message/state schemas; UUID/fingerprint contract; outbox; same-database decisions; simulator for add/edit/delete, dependencies, receipts, replay and crashes. G1–G8 within one generation. |
| J2 — Two-device experience | Transaction forms, splits/transfers, overlays, reports excluding pending work, review control lane, local delta exchange and snapshot repair. Phone/PC screen acceptance. |
| J3 — Real capture | SMS and CSV candidates, source identities, duplicate review, import batching, automatic writes journaled or explicitly disabled. Show measured bandwidth against whole-copy transfer. |
| J4 — Internet channel | Cloudflare queues, resumable snapshots, bounded background work, push, quotas and privacy note. Measure Doze/offline behavior and full cost; no latency promises from simulator results. |
| J5 — Trust and recovery | Registry, reviewed owner-authorization construction, cooperative move, lost-home recovery, transport-key rotation, restored identities and retired-branch reconciliation. Complete fault/security gates before enabling replacement. |
| J6 — Product cutover | All writable areas covered, compatible upgrades and backups, ordinary Windows/Android acceptance, Mohab's year, security/durability review. Freeze legacy lends; receive all returns or explicitly retain stranded copies; take a verified baseline; pair/upgrade peers into the new protocol. Never run v1 lending and this protocol on one live profile. |

**J6 build order (Claude, 2026-10-16).** J6 is built in steps, each merged when green:

| Step | Deliverable |
|---|---|
| J6a — Generic exact effects (built) | One replicator for every synchronized table: UUID row identity (integer ids via `journal_ids`, other keys as key columns with references mapped), touched-row triggers, typed row upserts/deletes in reference order, per-row fingerprint. Cash becomes the first area on it. |
| J6b — Checkpoint baselines (built) | Every replica, including the lab and tests, starts from the home's verified checkpoint; independent baselines are retired. |
| J6c — Areas (in progress: cash, master data, currency and reserves, plans and budgets) | Command families with field groups and service preconditions: master data (accounts, categories, counterparties, rules), foreign currency and conversions, plans/bills/loans/reserves/budgets, investments, shared settings. |
| J6d — Home automation | Rules, price fills, bill matching and revaluation run only on the home and commit as effects. |
| J6e — Upgrades and backups | Migration barrier, per-release compatibility table, journal-profile backup and restore. |
| J6f — Cutover (started: the app's screens run on a journal profile through `proxy.JournalServices`) | Convert a v1 profile (freeze lends, receive returns, verified baseline), pair peers, Mohab's year on a journal profile, Windows/Android acceptance, security/durability review. |

No borrowing fallback inside a journal profile. An area still awaiting coverage remains disabled there; the ordinary v1 profile stays on its existing implementation until cutover. A stranded pre-journal copy is preserved for explicit comparison/import, never guessed into an operation history.

## 11. Acceptance

Seeded simulation checks invariants after every transition, not just after successful catch-up. Include packet loss, duplicate and out-of-order delivery, concurrent requests, divergent clocks, disk-full/flush failures, process crashes and revocation. Eventual-convergence tests explicitly restore communication and resolve review; they do not assume liveness while the home is unavailable.

| Case | Required evidence |
|---|---|
| Offline phone coffee and PC statement | Both survive restart locally; when the home returns, both get decisions and converge without moving authority. |
| Amount and category edited separately | Independent field groups merge; conflicting amount edits wait; clock skew changes no suggestion or decision. |
| Add then edit before either uploads | Causal tokens resolve; rejected parent rejects children with reasons; no missing sequence. |
| Review blocks the origin | Later edits show the blocker; separate review lane resolves it; other origins continue. |
| Repeated or altered identity | Identical retry has one effect; same identity with changed payload is refused. Repeat after history pruning and snapshot replacement. |
| Crash at every durable boundary | Saved proposal, inbox, ledger effects, receipt and applied cursor recover consistently; no acknowledged operation disappears. |
| Replica on different rules/version | Exact effects converge without rerunning rules; unsupported effect schema stops before writes. |
| Category alias and deletion | Dependent edits follow canonical UUID; stale deletes/updates never recreate removed money. |
| SMS versus CSV and rent posted twice | Fuzzy match waits before a second posting; exact proven match links once; bill settlement and its payment stay atomic. |
| Snapshot amid pending edits | Verified promotion preserves the queue and unseen decisions; overlay rebuilt; fingerprint matches. |
| Phone sleeping or push lost | Save continues; status remains truthful; foreground/retry catches up. Test actual Android Doze and devices without Google services. |
| Local link and mailbox deliver together | One outcome and contiguous progress; interrupted chunks resume; acknowledgements mean durable receipt. |
| Wrong password/code or revoked origin | No pairing or new work; old queued envelopes cannot bypass membership; rotated keys exclude the removed device. |
| Graceful move interrupted at every phase | At most one activated successor; old home frozen durably; every accepted edit and receipt transfers. |
| Two simultaneous lost-home recoveries | Registry selects one successor by compare-and-swap; one owner secret, forged proof, or old transition nonce fails. |
| Old home and peer offline during recovery | Stale branch is preserved, not mistaken for current authority; reconnection re-proposes missing originals and shows changed outcomes. |
| Old backup restored / device reinstalled | No origin-ID reuse; prefix receipts survive; old messages cannot overwrite newer authority state. |
| Device absent for months | Receipt and tombstone metadata prevent replay; unseen refusal remains available; snapshot plus current pending edits converges. |
| Mailbox full, expired, attacked or unavailable | Bounded resources, backoff and isolated device quotas; edits persist; local sync works subject to authority limits; no invented recovery time. |
| Upgrade or automatic write during sync | Migration barrier and journal coverage prevent unrecorded mutations; interrupted migration restores or blocks safely. |
| Legacy cutover | An outstanding lend cannot be ignored; no v1 path can reopen a converted profile for writes. |

Measure encoded bytes, round trips, replay time, snapshot frequency, storage growth and catch-up latency on a representative year and large import. A small edit exchanges only bounded protocol overhead and its new data. Release evidence includes focused tests, the full suite, `tests/test_two_devices.py`, `tests/test_mohab_year.py`, ordinary-PC/phone checks, and A16/Part C review for affected screens. Passing the simulator is not evidence for phone wake-up timing or physical power-loss survival.
