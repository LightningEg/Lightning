---
title: Automatic nearby discovery and number matching for local pairing
type: feature
area: devices
status: building
created: 2026-10-23
by: Codex
skills: feedback-review
---

## Report
Owner requests automatic PC/phone discovery while pairing is open, number matching with three distinct choices, no QR, and the profile password still entered on the PC. Build and merge to main are authorized. A separate request to replace the recovery key with an initially random editable four-digit PIN awaits clarification: pairing PIN versus password-recovery key.

## Investigation
Request: discovery currently requires Find; joining requires typing the home code, then confirming equal six-digit transcript digits. Causes: lightning/runtime/journal_pairing.py, lightning/runtime/journal_enrollment.py, lightning/sync/journal/pairing.py and both native enrollment and Devices UI. Preserve encrypted transport, transcript binding, explicit home approval and password proof after number verification. Support actual first enrollment, not only compatible dummy replicas. Keep cryptographic recovery unchanged pending the owner's answer.

## Fix
Branch codex/wifi-number-matching. Tests must reject wrong choices, transcript substitution, expiry and password proof before selection; verify discovery refresh and native first enrollment.
