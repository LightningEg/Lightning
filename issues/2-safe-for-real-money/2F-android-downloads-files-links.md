---
title: On Android, downloads, file inputs and outside links do nothing - no backup, export or CSV import from the phone
type: bug
area: android
status: ready
created: 2026-10-20
by: Claude
skills: guideline-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§4 Phone, Android shell), by reading `android/app/src/main/java/org/lightning/app/MainActivity.java`.
Not built or run on a device. Severity: high, because Back up does nothing on the phone.

- No `setDownloadListener`: Export all data, Prepare AI analysis, the import template and reference downloads, and Back up do nothing.
- No `WebChromeClient.onShowFileChooser`: file inputs are dead, so CSV statement import and the market.zip import cannot start. Profile import was not checked.
- `shouldOverrideUrlLoading` (line 121) swallows outside links silently; open them in the browser with an `ACTION_VIEW` intent.
- Back follows WebView history, then sends the app to the background; C03.4 says Back goes to Overview first.

What holds: only 127.0.0.1 over cleartext, other hosts 403, no file or content access, no backup, debugging off, insets padded, `adjustResize` set.

## Fix
Add a download listener that saves to Downloads through MediaStore, a file chooser, and an intent for outside links; then check each on a phone.
