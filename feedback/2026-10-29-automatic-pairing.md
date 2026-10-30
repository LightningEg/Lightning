# Automatic PC and phone pairing

Date received: 2026-10-29 · Reviewed: 2026-10-29
Product/build/surface: Lightning v1.5.1, device pairing
Source: user chat; no private device addresses or pairing codes retained

## Observations and themes

| ID | Observation | Expected outcome | Theme | Investigation verdict | Issue / disposition |
| --- | --- | --- | --- | --- | --- |
| FB1 | Pairing still requires typing an address and code. | Find the PC or phone automatically and confirm its identity. | Pairing entry points | Built: nearby flow is primary; physical LAN reachability remains unverified. | BT-4L; [navigation regression](../tests/test_pairing_entrypoints.py) |

One observation from one respondent.

## Dated follow-ups

- 2026-10-29: `profiles.html` still promotes `/profiles/connect`, whose GET/POST handlers in `runtime/app.py` use the older address/code lending protocol. The phone Settings and More links enter the corresponding older Devices page for profiles that have not enabled device editing. That phone page does not expose the conversion link available in Profile settings. Modern pairing lives at `/profiles/journal/join` and `/journal/devices`; its new-profile entry is labelled “Join your existing home”. The manual page never calls `nearby_devices`, so this observation alone does not establish a LAN broadcast failure. Preserve explicit profile conversion and trust confirmation.

- 2026-10-29: BT-4L promotes nearby enrollment on both profile pickers and the direct connect page, exposes explicit setup on healthy idle Devices screens, and retains address/code pairing in a secondary disclosure. Fourteen navigation tests cover English/Arabic, PC/phone, errors, pending/manual pairing, damaged records, active lending and no implicit conversion. Two existing nearby protocol/screen tests pass on local dummy devices. This does not prove physical PC/phone broadcast reachability. The v1.5.1 workaround is Profile settings → Edit from your devices on the current profile holder, then Devices; the other device uses Join your existing home.
