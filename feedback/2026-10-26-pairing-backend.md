# Pairing backend hardening

Date received: 2026-10-26 · Reviewed: 2026-10-26
Product/build/surface: local pairing, main 1b07257
Source: owner chat request following a source and fault-injection review; dummy profiles only

## Observations and themes

| ID | Observation | Expected outcome | Theme | Investigation verdict | Issue / disposition |
| --- | --- | --- | --- | --- | --- |
| FB1 | Lost proof reply leaves home approved and PC stuck at password | Resume after uncertain delivery and process exit | Recovery | Defect, reproduced | [4E regression tests](../tests/test_pairing_hardening.py) |
| FB2 | Identity keys are plain PEM with filesystem permissions | OS-protected credentials and safe migration | Credentials | Request, source confirmed | [4F credential tests](../tests/test_device_credentials.py) |
| FB3 | Untrusted requests can occupy or exhaust a pairing window | Bounded resource use and pending leases | Availability | Defect, source confirmed | [4G abuse/lease tests](../tests/test_pairing_hardening.py) |
| FB4 | Native Wi-Fi/lifecycle acceptance is incomplete | Automated faults plus executable physical-device checks | Evidence | Request | [4H acceptance kit](../tools/pairing_acceptance.py); [physical matrix](../reports/2026-10-26-pairing-hardening/evidence/acceptance.md) |
| FB5 | Custom handshake needs independent review | Separate design/security review and regression evidence | Security | Request | [4I independent review](../reports/2026-10-26-pairing-hardening/report.md) |

Five observations; one owner request. No distinct end-user respondent count is inferred.

## Dated follow-ups

2026-10-26: owner authorized all five work items. Recovery-key/PIN changes remain cancelled. Actual physical-device and professional external audit evidence must be reported separately.

2026-10-26: 4E/4G fixed with durable uncertainty recovery, nonce-bound current-membership receipts, bounded leases and owner-approved password verification; 4F built with native OS wrapping and atomic identity-preserving migration. 4H delivers executable process/network faults and a physical acceptance kit; physical checks remain under 4A acceptance. 4I internal independent design/security review findings are addressed by the linked regression tests. Actual handset and professional external-audit evidence remain unrun.
