---
title: Verify and publish the replacement Android signing key
type: owner
area: android
status: building
created: 2026-10-19
by: Claude
---

## Report
The old signing key is lost. The owner explicitly authorized replacement on 2026-10-21 and generated a new PKCS#12 key locally on Linux; no private key or password was sent to the AI.

## Investigation
The v1.4.0 tag passed Linux, Windows and unsigned Android build checks, but its signing job received none of the four required environment secrets; publishing was skipped. Its tag is retained unchanged.

## Fix
`codex/android-signing-reset` pins the owner's new public fingerprint in `packaging/android-test-certificate.sha256` and prepares v1.4.1. The key and password stay with the owner; the four values must be installed in the `android-signing` environment. Publishing needs `LIGHTNING_DOWNLOADS_TOKEN` in `production-release`.

Finish only after signing verifies the new pin and both matched files are published. Existing Lightning Test installations need an independent backup before uninstalling and reinstalling; they cannot update in place across certificates. See Architecture › Build and release.
