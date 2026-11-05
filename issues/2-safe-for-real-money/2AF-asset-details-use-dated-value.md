---
title: Property and vehicle headlines must use the dated valuation
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

Opening 600,000; dated estimate 540,000; purchase 600,000; remaining loan 25,000. Header is 540,000, details value 600,000, change 0 and equity 575,000. Expected 540,000, -60,000 and 515,000. `_asset_view` uses ledger account_balance. Use the shared dated valuation with explicit currencies and as-of date; independently assert headline, change and equity rather than matching text anywhere in the HTML.

Evidence and acceptance: [desktop and phone UX audit, F1](../../reports/2026-11-05-desktop-phone-ux/report.md). Dummy data only. This is an audit finding; no implementation change is included.

