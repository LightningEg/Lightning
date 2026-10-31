---
title: The website APK still cannot be downloaded on the owner's phone
type: bug
look: technical
severity: medium
pillar: reach
size: M
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

**2026-10-28 (Claude):** the site's v1.5.0 Android link answers 302 to GitHub's asset store, then 200 with `application/vnd.android.package-archive`, `Content-Disposition: attachment` and 35.8 MB, with an Android Chrome user agent. The server side works; what remains is on the phone (browser download block, "file might be harmful", or install permission). Needs the phone's browser and the exact message.
