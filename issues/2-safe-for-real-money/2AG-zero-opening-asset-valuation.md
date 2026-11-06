---
title: A dated Other asset estimate must count after a zero opening
type: bug
look: technical
severity: high
pillar: own
size: M
status: new
created: 2026-11-05
by: Codex
skills: guideline-audit
app_version: 1.5.4
commit: a7ff8d8
repo: app
post: no
---

## Report

Create an Other asset at zero, then save a dated 540,000 estimate. History retains it but reported value remains zero. Reporting `_holdings` skips zero quantities before looking up manual valuation. Include eligible manually valued assets without fabricating cash. Verify revised estimates, account/wealth agreement and unchanged cash activity.

Evidence and acceptance: [desktop and phone UX audit, F2](../../reports/r24-desktop-phone-ux/report.md). Dummy data only. This is an audit finding; no implementation change is included.

