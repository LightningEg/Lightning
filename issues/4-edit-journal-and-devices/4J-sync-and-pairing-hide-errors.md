---
title: Sync and pairing hide their errors - a revoked or refused device looks like "home offline" forever
type: bug
look: technical
area: devices
status: ready
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

Severity: high (a device can silently stop syncing). Audit 9 B1-B4: `../../reports/2026-10-28-loose-ends-and-linking/report.md`. These are files under the journal claim in `NOW.md`; its holder builds this or hands it over.

## 4J1 Keep and show the last sync error

`runtime/journal_profile.py:281-284` passes on every `JournalError`/`OSError`/`TimeoutError`; `runtime/journal_android.py:58` maps any exception to offline; `sync/journal/device.py:334-337` reports only time and count. Store the last error class and message, show it on Devices, and give Android a distinct refused/revoked state that stops retrying.

## 4J2 A revoked device says it is no longer paired

`runtime/journal_pairing.py:52` decides "paired" from the device's own membership copy, so after `revoke()` (`:169-177`) the removed device keeps "This device is paired" (`journal_views/devices.html:38`). Inferred, not run: reproduce first. 4A §7 promises revocation is learned on contact.

## 4J3 Clocks a minute apart cannot pair

`sync/journal/pairing.py:76-78` accepts an offer only within 600 + 60 s of the joiner's clock; a phone more than a minute behind gets "offer expired or home identity changed". Say "the clocks differ", and bound by the home's own deadline.

## 4J4 Mid-way expiry and screen failures

`runtime/journal_ui_routes.py:150-159` swallows `resume()`/`finish()` errors, the joiner stays pending; `:47-49` shows any `screen()` failure as "pairing disabled"; `journal_profile.py:278` hides a failed discovery bind.

## Fix

Tests for each step: the background loop and Android worker given a `JournalError`, a revoked device's own screen, negative and one-hour skew, the joiner after expiry, `screen()` raising inside render.
