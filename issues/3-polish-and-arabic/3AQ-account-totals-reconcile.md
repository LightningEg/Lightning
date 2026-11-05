---
title: Accounts totals and ownership explanations must reconcile
type: bug
look: visual
severity: medium
pillar: understand
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

Sample More says Accounts 275,671 while Accounts says 261,671 including 10,000 held for others, so you own 265,671. Difference is 14,000 gam'eya still to pay. Unify label definitions and reconcile assets and liabilities explicitly across Accounts, sidebar, Overview and More without blindly changing the wealth formula.

Evidence and acceptance: [desktop and phone UX audit, F4](../../reports/2026-11-05-desktop-phone-ux/report.md). Dummy data only. This is an audit finding; no implementation change is included.

