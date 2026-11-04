---
title: Feedback form: submit scrolls to the page end, images take 10 s, and the survey forms accept formula injection and spam
type: tech
pillar: reach
size: M
status: ready
post: no
created: 2026-10-16
by: Claude Sonnet 5.5
skills: feedback-review
app_version: 1.1.0b1
commit: 8f478a2
repo: website
---

## Report
Feedback batch 004, tickets 111 and 112 (the website repo is outside this session's scope, so not built here).
- Submit jumps to the end of the page and image upload still takes about 10 s; people may close the page before it finishes. Keep the flow; upload each image as it is chosen (ticket 88's idea) and show a clear "sent" state in place.
- The survey, signup and feedback receivers must neutralise cells that start with `=`, `+`, `-` or `@` (formula injection), cap field lengths, and add a honeypot field and a rate limit against spam.
Severity: medium (the sheet is opened by the owner).

## Investigation · 2026-11-04

- [Website PR #162](https://github.com/LightningEg/Lightning_website/pull/162) implements uploading each selected image into a bounded six-hour cache, then using session-bound, single-use tokens to save submitted images to private Drive storage. English and Arabic pages disclose the upload timing. Receiver tests cover quota, session isolation, expiration, retry and image validation; Chromium tests exercise upload-on-selection, failed-send restoration, expiration and scroll position against a mocked receiver.
- Receiver source tests confirm formula escaping, field/image caps, a honeypot, deduplication and rate limits. This is source-level evidence, not evidence about the deployed script. The connected Drive exposed the target spreadsheet but no Apps Script project or script-deployment capability; live deployment and dummy-data acceptance are unverified. The website's `tools/deploy_receiver.py` can prepare a complete replacement bundle and backs up the existing project before deployment.
- The owner will deploy the prepared receiver. Deploy it before publishing website PR #162, then verify in a real browser that cross-origin acknowledgements work, a dummy image uploads on selection, submission reaches the expected spreadsheet and private Drive folder, and refused submissions retain their data. Close only after live acceptance. The security audit IT-1E tracks related receiver deployment and analytics-key rotation.
