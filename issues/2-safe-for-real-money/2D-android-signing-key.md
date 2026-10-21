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
The v1.4.0 tag passed Linux, Windows and unsigned Android build checks, but its signing job received none of the four required environment secrets; publishing was skipped. Its tag is retained unchanged. The owner then confirmed the four correctly named secrets and protection rules in android-signing. v1.4.1 still received empty values because the reusable workflow caller omitted the secret mappings; GitHub requires those mappings even for environment-only values (GitHub Docs › Reuse workflows › Using inputs and secrets).

## Fix
`codex/android-signing-reset` pinned the owner's new public fingerprint in `packaging/android-test-certificate.sha256`. `codex/android-environment-secret-mapping` prepares v1.4.2 with four explicit caller mappings and required called-workflow declarations. The Gradle job still does not reference secrets; no broad inheritance is used. v1.4.0 and v1.4.1 tags stay unchanged. The key and password stay with the owner; the four values must be installed in the `android-signing` environment. Publishing needs `LIGHTNING_DOWNLOADS_TOKEN` in `production-release`.

Finish only after signing verifies the new pin and both matched files are published. Existing Lightning Test installations need an independent backup before uninstalling and reinstalling; they cannot update in place across certificates. See Architecture › Build and release.
