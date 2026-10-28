---
title: Paid themes - the night switch resets, held colour too faint on light themes, PC cache numbers by hand
type: bug
look: technical
area: appearance
status: ready
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: both
---

## Report

Severity: low. Audit 9 part A: `../../reports/2026-10-28-loose-ends-and-linking/report.md`.

Done 2026-10-28 (branch `claude/audit-9-quick-fixes`): a licence survives a version bump and skips items this app lacks (`tests/test_cosmetic_licenses.py::test_a_licence_survives_a_theme_version_bump_and_skips_what_this_app_lacks`); the profile runtime test runs (`tests/test_theme_build.py::test_runtime_contract`); the registry is read once; 429 and 5xx get their own messages and Settings says "on this device" when sharing waited (`tests/test_theme_entitlements.py`); Architecture and the theme kit describe paid themes as built. Left: the steps below, and a manifest-version rule in `guideline/themes.md` (both repos).

## 8U3 Keep the night switch across launches

`ui/static/theme-runtime.js:106-108` stores it in `localStorage`; the PC's origin changes every launch (`runtime/http.py:208`). Save it as a device setting and pass it in the head.

## 8U4 Held colour per theme

`#7FB2FF` is fixed for every theme (`theme-surfaces.css:58,88`), about 1.9:1 on Cotton and Dendera day. Generate a contrast-checked `--theme-held` in `build_themes.py`. With 8J §3.

## 8U5 One cache rule

PC stylesheets use hand-bumped `?v=` (`base.html:13-16`, `partials/theme_head.html:3-4`); the phone hashes content (`ui/web.py:446`). Licences are still verified up to three times per page (`web.py:455-456`): work `owned()` out once per request.

## 8U6 One marketplace link

The marketplace URL is written four times and always English (`settings/index.html:24`, `theme-runtime.js:45`, `desktop/window.py:154`, `MainActivity.java:81`).

## 8U7 Tier in the manifest

Tiers live only in `tests/test_theme_build.py:181`: add `tier` to manifests and check it in the build. `compose_parts` (`security/cosmetic_parts.py:83`) is unused and misses `dendera-night`.
