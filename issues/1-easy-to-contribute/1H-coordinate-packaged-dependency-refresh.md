---
title: Refresh packaged dependencies with matching native wheels and lockfiles
type: tech
area: tools
status: ready
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
