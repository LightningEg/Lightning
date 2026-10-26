# Pairing backend hardening and security review

Date: 2026-10-26 · Author/reviewer: Codex implementation review plus a separate design-review agent
Repository: app · Reviewed baseline: 1b072575b8add30059a731aaf385facf9cb5689d

## Scope and method

Local journal pairing, first enrollment, device identity storage, protocol admission and their failure boundaries. Dummy profiles only. A separate agent reviewed commitment/challenge/reveal and proposed fixes without writing implementation code. Root and a build agent implemented and tested the findings. This is an independent internal source/design review; no professional external cryptographic certification or physical-device acceptance is implied.

## Findings

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| P1 | medium | Home admission followed by a lost proof reply strands the client; state and replies must reconcile after interruption | Original fault injection: home member exists, client password stage, retry and finish both refuse | 4E: durable handshake/proving states and authenticated receipts |
| P2 | high | Retrying a revealed joining secret against a changed challenge would allow offline number grinding; pin the first authenticated challenge before reveal | Independent ordering review | 4E/4I: immutable request, challenge and reveal; substitution regression |
| P3 | medium | Cached approvals and enrollment must enforce expiry, current authority and current membership, including revocation and latest transport epoch | Shared receipt validation review | 4E/4I: bounded current-membership receipts |
| P4 | medium | Raw identity PEM relies on filesystem permissions; native copies need OS-bound wrapping without identity changes | Existing DeviceIdentity key storage | 4F: DPAPI/Keystore, atomic migration, encrypted TLS temporary files |
| P5 | medium | Untrusted requests occupy slots or exhaust attempt budgets; failed-password budgets must not be consumed before owner approval | Pending-slot and proof-order review | 4G: pre-mutex bounds, nonrenewable leases, signed cancellation, deferred proof verification |
| P6 | medium | Builds/browser checks do not establish real Wi-Fi, firewall or Android lifecycle behavior | Existing acceptance boundary in 4A | 4H: automated fault kit and explicit native/physical matrix |

## Validation and limits

Software verification is recorded in the dated follow-up below. Identity wrapping protects files at rest: DPAPI binds to the Windows user; Android uses an app-owned non-exportable AES wrapping key. The P-256 signing/TLS key is unwrapped into process memory, so this does not claim non-exportable signing or protection against a compromised running process. Linux remains an explicit development host with private-file storage.

TLS loads only random-password-encrypted temporary PEM and removes it after loading. Portable private material is exported only inside the already-encrypted journal backup. OS-bound files copied to another device/account must fail closed and use explicit recovery/fresh enrollment. Recovery-key/password schemes are unchanged.

## Dated follow-ups

2026-10-26: implementation and automated verification in progress. Windows DPAPI execution is required in the Windows review-build job. Android Keystore execution is available through the debug-only dummy credential probe; actual handset Wi-Fi/sleep/process-death tests and any professional external audit remain unrun until evidence is supplied.

2026-10-26: automated [acceptance results](evidence/automated-acceptance.json) pass five actual process-exit/restart boundaries and three real loopback UDP/TLS cases, plus an explicitly labelled Linux development credential check. [The physical matrix](evidence/acceptance.md) keeps handset Wi-Fi, hotspot, firewall, sleep and reboot evidence unrun. Chromium native/harness journeys passed at desktop and narrow phone widths; credential migration, TLS, current-membership receipts, cancellation, expiry and no-preapproval-password-oracle tests passed.

The full local run completed with 2,586 passed, 11 skipped and eight failed. One failure was the Android adapter import placement introduced by this work; it was fixed by injecting the bridge from Android-only code, and its build-contract/adapter regressions pass. Six chart-browser failures reproduce on unchanged main. The guideline-mirror test initially saw a stale website checkout; after refreshing it, the remaining themes.md difference also reproduces against unchanged main. [Baseline comparison](evidence/baseline-checks.json) records those unrelated 3AH/8J acceptance boundaries; pairing changes do not alter guidelines or chart screens. Corrected/final targeted checks and clean-runner CI validate the final commit separately.

A final device-clock review adds a bounded one-minute future-clock allowance to client offer validation, while the home keeps its exact ten-minute admission deadline. Expired offers, excessive future dates and malformed expiry types remain refused (`tests/test_pairing_clocks.py`). Device identity protection remains separate from profile data-key wrapping; no password/recovery schema was changed.

2026-10-26: the actual Windows runner [native DPAPI probe](evidence/windows-dpapi.json) passed identity reload, OS-protected storage, wrong-binding/tamper rejection and encrypted TLS loading. The first Windows job then caught an integration-test fixture incorrectly substituting a fake protector for an already DPAPI-wrapped key. The fixture now preserves the native provider; production wrong-provider rejection remains unchanged. Android review APK compilation/verification passed; Android Keystore execution on a handset remains unrun.
