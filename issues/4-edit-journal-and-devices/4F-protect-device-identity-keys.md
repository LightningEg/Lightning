---
title: Protect device identity keys with Windows DPAPI and Android Keystore
type: tech
area: security
status: building
created: 2026-10-26
by: Codex
skills: feedback-review
---

## Report
DeviceIdentity currently stores unencrypted private PEM. Protect new and existing identities without changing their device ID, certificate or public key; fail closed on corruption or unavailable platform secrets. Keep TLS and encrypted backups compatible. Linux may retain explicit development-only storage; Windows and Android must not silently fall back to plaintext.

## Investigation
Owner authorized all improvements after backend review. No financial calculations or password/recovery-key scheme change.

## Fix
Design pending independent review.
