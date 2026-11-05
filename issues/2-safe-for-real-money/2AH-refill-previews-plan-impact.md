---
title: Emergency refill must preview and protect the remaining plan
type: bug
look: technical
severity: high
pillar: plan
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

On the 2026-11-05 demo, proposed refill 67,368.36 reduces free cash to zero and Safe to spend from 51,420.11 to -15,948.25. No cash transfer occurs, but the recommendation allocates cash needed elsewhere. Recompute the complete after-state, suggest an amount preserving commitments, show the consequence before confirmation, and provide an explicit larger-allocation choice. Use the isolated refill-baseline evidence.

Evidence and acceptance: [desktop and phone UX audit, F3](../../reports/2026-11-05-desktop-phone-ux/report.md). Dummy data only. This is an audit finding; no implementation change is included.

