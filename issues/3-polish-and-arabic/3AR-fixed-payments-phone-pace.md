---
title: Paid fixed obligations must not appear ahead of spending pace
type: bug
look: visual
severity: medium
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

Phone Budget on November 5 flags fully paid rent 12,000/12,000 and loan 2,500/2,500 as Ahead of pace and promotes them to attention rows. `_phone_categories` applies elapsed-month pace to all tracked categories. Distinguish scheduled settlement from variable spending, including mixed categories. Verify paid rent, variable groceries and excessive bills separately.

Evidence and acceptance: [desktop and phone UX audit, F5](../../reports/2026-11-05-desktop-phone-ux/report.md). Dummy data only. This is an audit finding; no implementation change is included.

