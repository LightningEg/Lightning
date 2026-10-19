---
title: Feedback form: submit scrolls to the page end, images take 10 s, and the survey forms accept formula injection and spam
type: tech
area: website
status: ready
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
