---
title: Explain which stale or pending inputs affect a financial figure
type: feature
pillar: understand
size: M
status: new
post: no
created: 2026-11-03
by: Codex
app_version: 1.5.4
commit: 89848dc0e4ce35bb18f72e861c7c620d8052fae4
repo: app
---

## Report

[Smart-feature recommendation 4](../../reports/2026-11-03-code-quality-and-smart-features/report.md). Existing price source/date metadata, account checking, journal status and figure explanations provide the foundation. Add contextual reasons when stale quotes/FX, pending edits or missing receipts affect a result; do not create a second competing total or invent a numeric confidence score.

## Fix

Create a Python read model of reason, source date, affected figure and resolution link. Extend the existing figure explanation surface on PC/phone, with a clear distinction between known and unknown freshness. Test stale/fresh prices, absent FX, pending confirmations and reconciled accounts; verify the explanation cannot change the amount. Coordinate with market and journal owners.

Not posted: proposal awaiting prioritization and shared freshness semantics.
