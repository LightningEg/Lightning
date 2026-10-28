---
title: Paid themes - a version bump locks out every buyer, one runtime test never runs, the night switch resets
type: bug
area: appearance
status: ready
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: both
---

## Report

Severity: high for 8U1 (paid themes lost after an update), low for the rest. Audit 9 part A: `../../reports/2026-10-28-loose-ends-and-linking/report.md`.

## 8U1 Licences survive a theme version bump

`security/cosmetic_license.py:77` refuses a licence unless `asset_version` equals the app's exactly (`ui/entitlements.py:43`), and `:78` refuses the whole licence for one unknown item. Accept any version up to the app's; say "Update Lightning" only for a newer one; skip unknown items. Test a bump. Add the manifest-version rule to `guideline/themes.md` (both repos).

## 8U2 Run the profile runtime test

`tests/theme-runtime-profile.test.cjs` (tried theme never stored, no unowned theme from another tab) is not run: `tests/test_theme_build.py:28` runs only `theme-runtime.test.cjs`.

## 8U3 Keep the night switch across launches

`ui/static/theme-runtime.js:106-108` stores it in `localStorage`; the PC's origin changes every launch (`runtime/http.py:208`). Save it as a device setting and pass it in the head.

## 8U4 Held colour per theme

`#7FB2FF` is fixed for every theme (`theme-surfaces.css:58,88`), about 1.9:1 on Cotton and Dendera day. Generate a contrast-checked `--theme-held` in `build_themes.py`. With 8J §3.

## 8U5 One cache rule, one registry read

PC stylesheets use hand-bumped `?v=` (`base.html:13-16`, `partials/theme_head.html:3-4`); the phone hashes content (`ui/web.py:446`). `entitlements.py:50,148` re-read the registry and verify licences up to three times per page (`web.py:455-456`).

## 8U6 Honest messages, one marketplace link

`entitlements.py:203` says "used or expired" for any non-409 error; `routes/settings.py:230` claims other devices got the unlock even when sharing failed (`entitlements.py:175`). The marketplace URL is written four times and always English (`settings/index.html:24`, `theme-runtime.js:45`, `desktop/window.py:154`, `MainActivity.java:81`).

## 8U7 Tier in the manifest; stale docs

Tiers live only in `tests/test_theme_build.py:181`: add `tier` to manifests and check it in the build. `compose_parts` (`security/cosmetic_parts.py:83`) is unused and misses `dendera-night`. `docs/ARCHITECTURE.md:526,532` and `theme-kit/README.md:133` still say entitlement and activation are unbuilt.
