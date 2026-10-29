---
title: On Android, downloads, file inputs and outside links do nothing - no backup, export or CSV import from the phone
type: bug
look: technical
severity: high
area: android
status: building
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

2026-10-29, built, not yet on a phone: every download (exports, the AI workbook, templates; GET or POST) is offered to the
system's "Save to" screen and the page comes back saying so (`lightning/runtime/phone_files.py`, `FileBridge.java`,
`tests/test_phone_downloads.py`); file fields open the system picker (`MainActivity.onShowFileChooser`). Left:

1. **Check on a phone:** Export all data, Prepare AI analysis, the import template, a CSV statement import and market.zip,
   in English and Arabic; cancel "Save to" once. Confirm a chosen file reaches the CSV import with `setAllowContentAccess(false)`.
2. **Backups never leave the phone.** Back up writes inside the app's private folder, so uninstalling or losing the phone loses
   them; there is no "Save a copy" of a backup on any screen. Offer the newest encrypted backup through the same "Save to".
3. Outside links other than the marketplace stay blocked on purpose (`MainActivity.storeLink`); Back still follows WebView
   history (C03.4 wants Overview first).
