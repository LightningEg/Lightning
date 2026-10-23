---
title: The website APK still cannot be downloaded on the owner's phone
type: bug
area: android
status: new
created: 2026-10-23
by: Codex
skills: website-sync
app_version: 1.4.4
commit: f4a52abb
repo: website
---

## Report

The owner reports that the APK still cannot be downloaded on their phone and explicitly asked to investigate later, after releasing v1.4.4 and updating the website download links.

This is a website-to-phone APK download report, distinct from the in-app WebView downloads in [2F](2F-android-downloads-files-links.md). It has not been reproduced. The phone model, browser, exact failing URL and error are unknown.

## Next investigation

Reproduce the website's Android download on the affected phone. Check the redirect chain and final APK response, browser download permissions and whether the failure happens during download or installation. Compare the direct release asset with the website button. Do not assume an installation or certificate issue without evidence.
