# Pairing backend hardening

Date received: 2026-10-26 · Reviewed: 2026-10-26
Product/build/surface: local pairing, main 1b07257
Source: owner chat request following a source and fault-injection review; dummy profiles only

## Observations and themes

| ID | Observation | Expected outcome | Theme | Investigation verdict | Issue / disposition |
| --- | --- | --- | --- | --- | --- |
| FB1 | Lost proof reply leaves home approved and PC stuck at password | Resume after uncertain delivery and process exit | Recovery | Defect, reproduced | [4E](../issues/4-edit-journal-and-devices/4E-pairing-lost-approval-reply.md) |
| FB2 | Identity keys are plain PEM with filesystem permissions | OS-protected credentials and safe migration | Credentials | Request, source confirmed | [4F](../issues/4-edit-journal-and-devices/4F-protect-device-identity-keys.md) |
| FB3 | Untrusted requests can occupy or exhaust a pairing window | Bounded resource use and pending leases | Availability | Defect, source confirmed | [4G](../issues/4-edit-journal-and-devices/4G-bound-pairing-slot-abuse.md) |
| FB4 | Native Wi-Fi/lifecycle acceptance is incomplete | Automated faults plus executable physical-device checks | Evidence | Request | [4H](../issues/4-edit-journal-and-devices/4H-pairing-fault-and-device-acceptance.md) |
| FB5 | Custom handshake needs independent review | Separate design/security review and regression evidence | Security | Request | [4I](../issues/4-edit-journal-and-devices/4I-review-pairing-handshake.md) |

Five observations; one owner request. No distinct end-user respondent count is inferred.

## Dated follow-ups

2026-10-26: owner authorized all five work items. Recovery-key/PIN changes remain cancelled. Actual physical-device and professional external audit evidence must be reported separately.
