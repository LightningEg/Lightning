---
title: Refresh packaged dependencies with matching native wheels and lockfiles
type: tech
pillar: build
size: L
status: building
created: 2026-10-23
by: Codex
skills: stale-check
app_version: 1.4.3
commit: fdbea6b
repo: app
---

## Report

PR #103 updates Python dependency inputs but leaves Android and desktop lockfiles unchanged. Its CI fails `test_the_lock_pins_every_package_as_one_file_from_the_published_wheels`. The proposed sqlcipher3, cffi and pydantic-core versions also differ from the Android native-wheel build matrix. Merging would leave different dependency sets in development and shipped builds.

## Fix

Refresh the Android native-wheel matrix and obtain matching verified wheels through the existing owner-controlled build/publication workflow. Regenerate Android, desktop and build-tool locks together; verify all hashes, the phone package contract and the full application suite. Review pure-Python and build-tool security updates as part of that coordinated refresh. Keep existing validated pins until then. The closed PR #103 and its branch preserve the proposed versions.

## Coordinated refresh — 2026-10-29

Stage 1 prepares the native-wheel recipe for sqlcipher3 0.6.4, cffi 2.1.1 and
pydantic-core 2.50.2; cryptography stays at 50.0.2. Each source archive is pinned
by SHA-256 and verified before extraction or build. The existing SQLCipher Conan
and Android liblog patch anchors were checked against the 0.6.4 source.

App inputs and installed locks deliberately keep the validated wheel set until
the new native wheels are built and published through the existing workflow.
After merging the recipe, run `android-native-wheels.yml` on main, verify the
link/16 KB checks and publish that successful run using `publish_run`. Then:

1. Update dependency inputs together (including encrypted/desktop extras and
   developer requirements); resolve Pydantic with core 2.50.2 rather than assuming
   the newest Pydantic matches it.
2. Regenerate Android with `tools/android_lock.py` using the published SHA256SUMS;
   regenerate both desktop locks and the build-tools lock with their recorded uv
   commands. Verify downloaded hashes and review dependency advisories.
3. Run package-contract tests, the full application suite and import contracts;
   run native Windows/Android build checks for the changed package set.

This item stays open until those stages pass. No app release or signing is part
of the native-wheel recipe preparation.

Local preparation also resolves candidate Windows/Linux and build-tool locks,
and the Android graph with Pydantic 2.14.2/core 2.50.2. The candidate Linux
environment installs with required hashes; all four import contracts pass. All
18 non-native Android wheels were downloaded and their hashes verified. PyPI
advisory metadata reports none for the 53 candidate packages checked. The four
native packages have no compatible Android wheels on PyPI, so the repository's
build/publication stage is required before the installed locks can change.

Validation of the recipe-preparation branch: the full current-dependency suite
finished with 2,749 passed and 42 skipped. Its one failure is the pre-existing
app/website guideline mismatch (`guideline/app.html` and `app-ar.html`); neither
file changes on this branch. Import contracts and the generated issue check pass.

The owner authorized GitHub publication and the native-wheel workflow on
2026-10-29. Native builds and the coordinated lock update are in progress.

The upgraded candidate environment's full suite also finished with 2,749 passed
and 42 skipped, and the same single guideline-copy failure (507 seconds, versus
548 seconds with current dependencies). No additional failures were observed.
The post-record issue/document checks pass with the known mirror check excluded.
Native Windows/Android build and runtime validation remains outstanding.

## 1H1 Build and publish the native wheels · L
Merge the recipe, run `android-native-wheels.yml` on main, verify the link and 16 KB checks and publish the run with `publish_run`. Claimed by Codex.

## 1H2 Update the dependency inputs together · M
Encrypted and desktop extras and developer requirements; resolve Pydantic with core 2.50.2, not the newest Pydantic.

## 1H3 Regenerate the locks · M
`tools/android_lock.py` with the published SHA256SUMS, both desktop locks and the build-tools lock with their recorded uv commands; verify hashes and advisories.

## 1H4 Validate · M
Package-contract tests, the full suite and import contracts; native Windows and Android build checks for the changed packages.
