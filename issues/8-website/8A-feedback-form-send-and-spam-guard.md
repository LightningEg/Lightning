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

- The browser prepares selected images immediately, returns the form while delivery runs in the background, displays confirmed delivery, and restores a ticket and its images after a failed send. [Website PR #162](https://github.com/LightningEg/Lightning_website/pull/162) exercises the image payload, failed-send restoration and scroll position in Chromium against a mocked receiver; these checks pass.
- **Still open:** preparation is local; the image is uploaded only with the final submission. Reproduce the reported scroll issue in the real flow and decide whether the existing asynchronous send meets the original request or implement staged upload with safe cleanup and limits.
- Receiver source tests confirm formula escaping, field/image caps, a honeypot, deduplication and rate limits. This is source-level evidence, not evidence about the deployed script. The connected Drive exposed the target spreadsheet but no Apps Script project or script-deployment capability; live deployment and dummy-data acceptance are unverified. The website's `tools/deploy_receiver.py` can prepare a complete replacement bundle and backs up the existing project before deployment.
- Close only after the remaining UX is resolved and the live receiver's protections, readable response, and destination writes have been verified. The security audit IT-1E tracks related receiver deployment and analytics-key rotation.
